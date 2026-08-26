"""Stateful SMS/email world with optional model-backed simulated participants."""

from __future__ import annotations

import copy
import fcntl
import importlib.util
import json
import os
import tempfile
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

SUPPORTED_CHANNELS = {"sms", "email"}

ActionHandler = Callable[[dict[str, Any], dict[str, Any]], tuple[str, dict[str, Any]]]


class SidecarResponder(Protocol):
    def respond(
        self,
        *,
        conversation: dict[str, Any],
        outbound_message: dict[str, Any],
        world: dict[str, Any],
        current_time: str,
        rejection_feedback: str | None = None,
    ) -> dict[str, Any]: ...


class SidecarResponseRejected(ValueError):
    """Raised when a sidecar response requests an invalid world transition."""


class InteractionWorld:
    """Persist conversations and validate sidecar-requested world effects.

    The action vocabulary is task-owned: a task supplies a Python module whose
    ``ACTIONS`` maps action names to ``handler(world, data)`` callables returning
    ``(event_type, event_data)`` and raising ``ValueError`` on invalid transitions.
    Without an actions module, only the built-in ``none`` action is accepted.
    """

    def __init__(
        self,
        scenario: str | Path | dict[str, Any],
        state_path: str | Path,
        *,
        responder: SidecarResponder | None = None,
        actions_path: str | Path | None = None,
    ) -> None:
        self.scenario = scenario
        self.state_path = Path(state_path)
        self.lock_path = self.state_path.with_suffix(f"{self.state_path.suffix}.lock")
        self.responder = responder
        self.actions = _load_actions(actions_path) if actions_path else {}
        self._initialize()

    def list_conversations(
        self, channel: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        self._validate_channel(channel)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer from 1 through 100")
        with self._document() as document:
            conversations = [
                item
                for item in document["conversations"]
                if channel is None or item["channel"] == channel
            ]
            conversations.sort(
                key=lambda item: item["messages"][-1]["sent_at"], reverse=True
            )
            return [self._summarize(item) for item in conversations[:limit]]

    def search_conversations(
        self, query: str, channel: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        normalized = query.strip().casefold()
        if not normalized:
            raise ValueError("query must not be empty")
        matches = []
        for conversation in self.list_full_conversations(channel=channel):
            if normalized in json.dumps(conversation, ensure_ascii=False).casefold():
                matches.append(conversation)
        matches.sort(key=lambda item: item["messages"][-1]["sent_at"], reverse=True)
        return [self._summarize(item) for item in matches[:limit]]

    def list_full_conversations(
        self, channel: str | None = None
    ) -> list[dict[str, Any]]:
        self._validate_channel(channel)
        with self._document() as document:
            return copy.deepcopy(
                [
                    item
                    for item in document["conversations"]
                    if channel is None or item["channel"] == channel
                ]
            )

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        with self._document() as document:
            return copy.deepcopy(self._find_conversation(document, conversation_id))

    def reply_to_conversation(self, conversation_id: str, body: str) -> dict[str, Any]:
        normalized = body.strip()
        if not normalized:
            raise ValueError("body must not be empty")
        with self._document(write=True) as document:
            conversation = self._find_conversation(document, conversation_id)
            message = self._outbound_message(
                document,
                channel=conversation["channel"],
                recipients=conversation["participants"],
                body=normalized,
            )
            conversation["messages"].append(message)
            self._record_event(
                document,
                "message.outbound",
                message_id=message["id"],
                conversation_id=conversation_id,
                channel=conversation["channel"],
                recipient_addresses=[
                    item["address"] for item in conversation["participants"]
                ],
            )
            reply = self._simulate_reply(document, conversation, message)
            return self._message_result(conversation, message, reply)

    def send_message(
        self,
        channel: str,
        recipient_address: str,
        body: str,
        *,
        subject: str | None = None,
        recipient_name: str | None = None,
        organization: str | None = None,
    ) -> dict[str, Any]:
        self._validate_channel(channel)
        address = recipient_address.strip()
        normalized = body.strip()
        if not address or not normalized:
            raise ValueError("recipient_address and body must not be empty")
        if channel == "email" and "@" not in address:
            raise ValueError("email recipient_address must contain @")

        with self._document(write=True) as document:
            participant = {"address": address}
            if recipient_name and recipient_name.strip():
                participant["display_name"] = recipient_name.strip()
            if organization and organization.strip():
                participant["organization"] = organization.strip()
            conversation = {
                "id": f"{channel}-conversation-{uuid.uuid4().hex[:12]}",
                "channel": channel,
                "participants": [participant],
                "messages": [],
            }
            if channel == "email" and subject and subject.strip():
                conversation["subject"] = subject.strip()
            message = self._outbound_message(
                document,
                channel=channel,
                recipients=[participant],
                body=normalized,
            )
            conversation["messages"].append(message)
            document["conversations"].append(conversation)
            self._record_event(
                document,
                "message.outbound",
                message_id=message["id"],
                conversation_id=conversation["id"],
                channel=channel,
                recipient_addresses=[address],
            )
            reply = self._simulate_reply(document, conversation, message)
            return self._message_result(conversation, message, reply)

    def _initialize(self) -> None:
        if isinstance(self.scenario, dict):
            scenario = copy.deepcopy(self.scenario)
        else:
            scenario = json.loads(Path(self.scenario).read_text(encoding="utf-8"))
        if scenario.get("schema_version") != 1:
            raise ValueError("scenario must use schema_version 1")
        document = scenario
        document.setdefault("accounts", {})
        document.setdefault("conversations", [])
        for seed_name in document.pop("conversation_seeds", []):
            seed = json.loads(Path(seed_name).read_text(encoding="utf-8"))
            if seed.get("schema_version") != 1:
                raise ValueError("conversation seed must use schema_version 1")
            channel = seed["channel"]
            document["accounts"][channel] = seed["account"]
            for conversation in seed["conversations"]:
                imported = copy.deepcopy(conversation)
                imported["channel"] = channel
                document["conversations"].append(imported)
        document.setdefault("world", {})
        document.setdefault("events", [])
        document.setdefault("clock", datetime.now(UTC).isoformat())
        self._validate_document(document)

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            if not self.state_path.exists():
                self._write(document)
            else:
                self._validate_document(self._read())

    @contextmanager
    def _document(self, *, write: bool = False) -> Iterator[dict[str, Any]]:
        with self._lock():
            document = self._read()
            self._validate_document(document)
            yield document
            if write:
                self._validate_document(document)
                self._write(document)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write(self, document: dict[str, Any]) -> None:
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.state_path.parent,
                prefix=f".{self.state_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(document, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary_name = handle.name
            os.replace(temporary_name, self.state_path)
        finally:
            if temporary_name and Path(temporary_name).exists():
                Path(temporary_name).unlink()

    FEEDBACK_ATTEMPTS = 2
    FALLBACK_REPLY_BODY = "Sorry I can't help you."

    def _simulate_reply(
        self,
        document: dict[str, Any],
        conversation: dict[str, Any],
        outbound: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.responder is None:
            return None

        feedback: str | None = None
        for _ in range(1 + self.FEEDBACK_ATTEMPTS):
            try:
                kwargs = {} if feedback is None else {"rejection_feedback": feedback}
                response = self.responder.respond(
                    conversation=copy.deepcopy(conversation),
                    outbound_message=copy.deepcopy(outbound),
                    world=copy.deepcopy(document["world"]),
                    current_time=document["clock"],
                    **kwargs,
                )
            except (TypeError, ValueError) as error:
                # Malformed model output (unparseable JSON, wrong shape) is a
                # correctable response, not a provider failure: feed the error
                # back and retry so an engaged participant never goes silent.
                feedback = str(error) or type(error).__name__
                self._record_event(
                    document,
                    "sidecar.response_rejected",
                    outbound_message_id=outbound["id"],
                    error_type=type(error).__name__,
                )
                continue
            except Exception as error:  # noqa: BLE001 - isolate provider/transport failures
                self._record_event(
                    document,
                    "sidecar.failed",
                    outbound_message_id=outbound["id"],
                    error_type=type(error).__name__,
                )
                return None

            try:
                decision, sender, body, action = self._validate_sidecar_response(
                    response, conversation, outbound
                )
                if decision == "no_reply":
                    self._record_event(
                        document,
                        "sidecar.no_reply",
                        outbound_message_id=outbound["id"],
                    )
                    return None
                event_type, event_data = self._apply_action(document["world"], action)
            except (KeyError, TypeError, ValueError) as error:
                feedback = str(error) or type(error).__name__
                self._record_event(
                    document,
                    "sidecar.response_rejected",
                    outbound_message_id=outbound["id"],
                    error_type=type(error).__name__,
                )
                continue

            self._record_event(
                document,
                event_type,
                outbound_message_id=outbound["id"],
                sidecar_action=action["type"],
                **event_data,
            )
            self._enrich_participant(conversation, sender)
            return self._append_inbound(document, conversation, sender, body)

        # A participant that has engaged must not go silent after rejections.
        participant = conversation["participants"][0]
        sender = {
            "display_name": participant.get("display_name")
            or participant.get("organization")
            or participant["address"],
            "address": participant["address"],
        }
        if participant.get("organization"):
            sender["organization"] = participant["organization"]
        self._record_event(
            document,
            "sidecar.fallback_reply",
            outbound_message_id=outbound["id"],
        )
        return self._append_inbound(
            document, conversation, sender, self.FALLBACK_REPLY_BODY
        )

    def _append_inbound(
        self,
        document: dict[str, Any],
        conversation: dict[str, Any],
        sender: dict[str, str],
        body: str,
    ) -> dict[str, Any]:
        reply = {
            "id": f"{conversation['channel']}-msg-{uuid.uuid4().hex[:12]}",
            "direction": "inbound",
            "sender": copy.deepcopy(sender),
            "recipients": [
                copy.deepcopy(document["accounts"][conversation["channel"]])
            ],
            "body": body,
            "sent_at": self._tick(document),
            "delivery_status": "delivered",
        }
        conversation["messages"].append(reply)
        return copy.deepcopy(reply)

    @staticmethod
    def _validate_sidecar_response(
        response: dict[str, Any],
        conversation: dict[str, Any],
        outbound: dict[str, Any],
    ) -> tuple[str, dict[str, str], str, dict[str, Any]]:
        if not isinstance(response, dict):
            raise TypeError("sidecar response must be an object")
        if response.get("in_reply_to_message_id") != outbound["id"]:
            raise SidecarResponseRejected(
                "sidecar response references the wrong message"
            )
        decision = response.get("decision")
        if decision not in {"reply", "no_reply"}:
            raise SidecarResponseRejected("invalid sidecar decision")
        if decision == "no_reply":
            if response.get("body") is not None:
                raise SidecarResponseRejected("no_reply must not contain a body")
            return decision, {}, "", {"type": "none", "data": {}}

        body = response.get("body")
        if not isinstance(body, str) or not body.strip():
            raise SidecarResponseRejected("reply must contain a body")
        sender = response.get("sender")
        if not isinstance(sender, dict):
            raise SidecarResponseRejected("reply must identify its sender")
        address = sender.get("address")
        display_name = sender.get("display_name")
        if not isinstance(address, str) or not isinstance(display_name, str):
            raise SidecarResponseRejected("sender requires display_name and address")
        participant_addresses = {
            item["address"].casefold() for item in conversation["participants"]
        }
        if address.casefold() not in participant_addresses:
            raise SidecarResponseRejected("sender is not a conversation participant")
        normalized_sender = {"display_name": display_name.strip(), "address": address}
        organization = sender.get("organization")
        if isinstance(organization, str) and organization.strip():
            normalized_sender["organization"] = organization.strip()

        action = response.get("action")
        if not isinstance(action, dict) or not isinstance(action.get("data"), dict):
            raise SidecarResponseRejected("reply must contain a semantic action")
        return decision, normalized_sender, body.strip(), action

    def _apply_action(
        self, world: dict[str, Any], action: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        action_type = action.get("type")
        if action_type == "none":
            return "participant.replied", {}
        handler = self.actions.get(action_type)
        if handler is None:
            raise SidecarResponseRejected(
                f"unsupported sidecar action: {action_type!r}"
            )
        return handler(world, action["data"])

    @staticmethod
    def _enrich_participant(
        conversation: dict[str, Any], sender: dict[str, str]
    ) -> None:
        for participant in conversation["participants"]:
            if participant["address"].casefold() != sender["address"].casefold():
                continue
            participant.setdefault("display_name", sender["display_name"])
            if sender.get("organization"):
                participant.setdefault("organization", sender["organization"])
            return

    def _outbound_message(
        self,
        document: dict[str, Any],
        *,
        channel: str,
        recipients: list[dict[str, str]],
        body: str,
    ) -> dict[str, Any]:
        return {
            "id": f"{channel}-msg-{uuid.uuid4().hex[:12]}",
            "direction": "outbound",
            "sender": copy.deepcopy(document["accounts"][channel]),
            "recipients": copy.deepcopy(recipients),
            "body": body,
            "sent_at": self._tick(document),
            "delivery_status": "sent",
        }

    def _tick(self, document: dict[str, Any]) -> str:
        current = datetime.fromisoformat(document["clock"])
        current = current.astimezone(UTC) + timedelta(minutes=1)
        document["clock"] = current.isoformat()
        return document["clock"]

    def _record_event(
        self, document: dict[str, Any], event_type: str, **data: Any
    ) -> None:
        document["events"].append(
            {
                "id": f"event-{uuid.uuid4().hex[:12]}",
                "type": event_type,
                "at": document["clock"],
                **data,
            }
        )

    @staticmethod
    def _message_result(
        conversation: dict[str, Any],
        message: dict[str, Any],
        reply: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "conversation_id": conversation["id"],
            "message": copy.deepcopy(message),
            "delivery_status": "delivered",
            "new_inbound_message": reply is not None,
            "inbound_message": copy.deepcopy(reply),
        }

    @staticmethod
    def _find_conversation(
        document: dict[str, Any], conversation_id: str
    ) -> dict[str, Any]:
        for conversation in document["conversations"]:
            if conversation["id"] == conversation_id:
                return conversation
        raise KeyError(f"conversation not found: {conversation_id}")

    @staticmethod
    def _summarize(conversation: dict[str, Any]) -> dict[str, Any]:
        last = conversation["messages"][-1]
        preview = " ".join(last["body"].split())
        result = {
            "id": conversation["id"],
            "channel": conversation["channel"],
            "participants": copy.deepcopy(conversation["participants"]),
            "message_count": len(conversation["messages"]),
            "last_message_at": last["sent_at"],
            "last_message_direction": last["direction"],
            "last_message_preview": preview[:160],
        }
        if conversation.get("subject"):
            result["subject"] = conversation["subject"]
        return result

    @staticmethod
    def _validate_channel(channel: str | None) -> None:
        if channel is not None and channel not in SUPPORTED_CHANNELS:
            raise ValueError("channel must be email or sms")

    @staticmethod
    def _validate_document(document: dict[str, Any]) -> None:
        if document.get("schema_version") != 1:
            raise ValueError("world state must use schema_version 1")
        if not isinstance(document.get("accounts"), dict):
            raise TypeError("world state must define accounts")
        if not isinstance(document.get("conversations"), list):
            raise TypeError("world state must define conversations")
        conversation_ids: set[str] = set()
        message_ids: set[str] = set()
        for conversation in document["conversations"]:
            if conversation.get("channel") not in SUPPORTED_CHANNELS:
                raise ValueError("each conversation must have a supported channel")
            conversation_id = conversation.get("id")
            if not conversation_id or conversation_id in conversation_ids:
                raise ValueError("conversation IDs must be present and unique")
            conversation_ids.add(conversation_id)
            if not conversation.get("participants") or not conversation.get("messages"):
                raise ValueError("conversations require participants and messages")
            if any(
                not participant.get("address")
                for participant in conversation["participants"]
            ):
                raise ValueError("every participant must have an address")
            for message in conversation["messages"]:
                message_id = message.get("id")
                if not message_id or message_id in message_ids:
                    raise ValueError("message IDs must be present and unique")
                message_ids.add(message_id)
                if message.get("direction") not in {"inbound", "outbound"}:
                    raise ValueError("message direction must be inbound or outbound")
                if (
                    not isinstance(message.get("body"), str)
                    or not message["body"].strip()
                ):
                    raise ValueError("every message must have a body")
                if not message.get("sent_at"):
                    raise ValueError("every message must have a timestamp")


def _load_actions(path: str | Path) -> dict[str, ActionHandler]:
    spec = importlib.util.spec_from_file_location("world_actions", Path(path))
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"cannot load actions module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actions = getattr(module, "ACTIONS", None)
    if not isinstance(actions, dict) or not actions:
        raise ValueError("actions module must define a non-empty ACTIONS dict")
    if "none" in actions:
        raise ValueError("the 'none' action is built in and cannot be overridden")
    return dict(actions)
