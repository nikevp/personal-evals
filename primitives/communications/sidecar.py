"""On-demand model-backed participant responder for the interaction world."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Protocol

PROMPT_TEMPLATE = """\
# Hidden task and participant context

{context}

# Current logical time

{current_time}

# Current hidden world state

```json
{world}
```

# Conversation including the latest outbound message

```json
{conversation}
```

# Latest outbound message

```json
{outbound_message}
```

# Required response schema

```json
{schema}
```

{extension_sections}{feedback_section}Use exactly one semantic action. Never \
return arbitrary state paths."""

FEEDBACK_SECTION_TEMPLATE = """\
# Previous response rejected

The runtime rejected your previous response to this message: {reason}
Return a corrected response that satisfies the schema and the context rules.

"""


class SidecarExtension(Protocol):
    """Task-selected hook adding prompt sections and post-processing replies."""

    def prompt_sections(self) -> dict[str, str]: ...

    def post_process(self, response: dict[str, Any]) -> dict[str, Any]: ...


def load_extension(path: str | Path) -> SidecarExtension | None:
    """Load a task extension module and call its ``create_extension`` factory."""
    spec = importlib.util.spec_from_file_location("sidecar_extension", Path(path))
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"cannot load sidecar extension module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "create_extension", None)
    if not callable(factory):
        raise TypeError("sidecar extension module must define create_extension()")
    return factory()


class SidecarAgent:
    """Create one isolated model response for each outbound communication."""

    INSUFFICIENT_CONTEXT_REPLY = "Sorry I can't help you."

    def __init__(
        self,
        context_path: str | Path,
        schema_path: str | Path,
        *,
        model: str,
        extension: SidecarExtension | None = None,
        client: Any | None = None,
    ) -> None:
        self.context = Path(context_path).read_text(encoding="utf-8")
        self.schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        self.model = model
        self.extension = extension
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client

    def respond(
        self,
        *,
        conversation: dict[str, Any],
        outbound_message: dict[str, Any],
        world: dict[str, Any],
        current_time: str,
        rejection_feedback: str | None = None,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(
            conversation=conversation,
            outbound_message=outbound_message,
            world=world,
            current_time=current_time,
            rejection_feedback=rejection_feedback,
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=0,
            system=(
                "You are a hidden communications sidecar in a Harbor evaluation. "
                "Simulate only the external participant addressed by the latest "
                "message. Follow the supplied task context exactly. Return only one "
                "JSON object matching the supplied schema, without markdown fences."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        parsed = self.parse_response(text)
        decision = parsed.get("decision")
        if decision == "no_reply":
            return parsed
        if decision == "reply":
            if self.extension is not None:
                return self.extension.post_process(parsed)
            return parsed
        return self._fallback_reply(conversation, outbound_message)

    def _build_prompt(
        self,
        *,
        conversation: dict[str, Any],
        outbound_message: dict[str, Any],
        world: dict[str, Any],
        current_time: str,
        rejection_feedback: str | None = None,
    ) -> str:
        extension_sections = ""
        if self.extension is not None:
            for title, body in self.extension.prompt_sections().items():
                extension_sections += f"# {title}\n\n{body}\n\n"
        feedback_section = ""
        if rejection_feedback:
            feedback_section = FEEDBACK_SECTION_TEMPLATE.format(
                reason=rejection_feedback
            )
        return PROMPT_TEMPLATE.format(
            context=self.context,
            current_time=current_time,
            world=json.dumps(world, indent=2, ensure_ascii=False),
            conversation=json.dumps(conversation, indent=2, ensure_ascii=False),
            outbound_message=json.dumps(outbound_message, indent=2, ensure_ascii=False),
            schema=json.dumps(self.schema, indent=2, ensure_ascii=False),
            extension_sections=extension_sections,
            feedback_section=feedback_section,
        )

    @classmethod
    def _fallback_reply(
        cls,
        conversation: dict[str, Any],
        outbound_message: dict[str, Any],
    ) -> dict[str, Any]:
        """Turn an unusable model decision into the required safe reply."""
        participants = conversation.get("participants", [])
        if not participants:
            raise ValueError("sidecar conversation must identify a participant")
        participant = participants[0]
        display_name = (
            participant.get("display_name")
            or participant.get("organization")
            or participant["address"]
        )
        sender = {
            "display_name": display_name,
            "address": participant["address"],
        }
        if participant.get("organization"):
            sender["organization"] = participant["organization"]
        return {
            "decision": "reply",
            "in_reply_to_message_id": outbound_message["id"],
            "sender": sender,
            "body": cls.INSUFFICIENT_CONTEXT_REPLY,
            "action": {"type": "none", "data": {}},
        }

    @staticmethod
    def parse_response(text: str) -> dict[str, Any]:
        normalized = text.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            normalized = "\n".join(lines).strip()
        value = json.loads(normalized)
        if not isinstance(value, dict):
            raise TypeError("sidecar response must be a JSON object")
        return value
