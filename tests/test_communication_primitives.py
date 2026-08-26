from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest

from primitives.communications import InteractionWorld

ACCOUNTS = {
    "sms": {"display_name": "Jordan Reyes", "address": "+15555550100"},
    "email": {"display_name": "Jordan Reyes", "address": "jordan@example.com"},
}


def write_seed(tmp_path: Path, channel: str) -> Path:
    sender = {
        "display_name": "Casey Lin",
        "address": "casey@vendor.example" if channel == "email" else "+15555550111",
    }
    conversation: dict[str, Any] = {
        "id": f"{channel}-conversation-casey",
        "participants": [sender],
        "messages": [
            {
                "id": f"{channel}-msg-0001",
                "direction": "inbound",
                "sender": sender,
                "recipients": [ACCOUNTS[channel]],
                "body": "Hello, following up on the delivery window.",
                "sent_at": "2026-08-20T09:00:00+00:00",
                "delivery_status": "delivered",
            }
        ],
    }
    if channel == "email":
        conversation["subject"] = "Delivery window"
    seed_path = tmp_path / f"{channel}.json"
    seed_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": channel,
                "account": ACCOUNTS[channel],
                "conversations": [conversation],
            }
        ),
        encoding="utf-8",
    )
    return seed_path


def channel_world(tmp_path: Path, channel: str, **kwargs: Any) -> InteractionWorld:
    seed_path = write_seed(tmp_path, channel)
    scenario = {"schema_version": 1, "conversation_seeds": [str(seed_path)]}
    return InteractionWorld(scenario, tmp_path / f"{channel}-state.json", **kwargs)


@pytest.mark.parametrize("channel", ["sms", "email"])
def test_seed_can_be_listed_searched_and_retrieved(
    tmp_path: Path, channel: str
) -> None:
    world = channel_world(tmp_path, channel)

    summaries = world.list_conversations(channel=channel)
    assert [item["id"] for item in summaries] == [f"{channel}-conversation-casey"]

    assert world.search_conversations("delivery window", channel=channel)
    assert world.search_conversations("Casey Lin", channel=channel)
    assert world.search_conversations("not present", channel=channel) == []
    assert world.get_conversation(f"{channel}-conversation-casey")["messages"]


def test_reply_is_persisted_and_silent_without_responder(tmp_path: Path) -> None:
    world = channel_world(tmp_path, "email")

    result = world.reply_to_conversation(
        "email-conversation-casey", "The delivery postcode is 10013."
    )

    assert result["message"]["direction"] == "outbound"
    assert result["new_inbound_message"] is False
    assert result["inbound_message"] is None

    seed_path = tmp_path / "email.json"
    restarted = InteractionWorld(
        {"schema_version": 1, "conversation_seeds": [str(seed_path)]},
        tmp_path / "email-state.json",
    )
    messages = restarted.get_conversation("email-conversation-casey")["messages"]
    assert messages[-1]["body"] == "The delivery postcode is 10013."
    assert len(messages) == 2


@pytest.mark.parametrize(
    ("channel", "recipient", "subject"),
    [
        ("email", "quotes@example.test", "Painting shipping quote"),
        ("sms", "+85255550123", None),
    ],
)
def test_send_message_starts_persisted_outbound_conversation(
    tmp_path: Path, channel: str, recipient: str, subject: str | None
) -> None:
    world = channel_world(tmp_path, channel)

    result = world.send_message(
        channel,
        recipient,
        "Please provide an itemized quote.",
        subject=subject,
        recipient_name="Quotes Team",
        organization="Example Logistics",
    )

    conversation = world.get_conversation(result["conversation_id"])
    assert conversation["participants"][0] == {
        "address": recipient,
        "display_name": "Quotes Team",
        "organization": "Example Logistics",
    }
    assert conversation["messages"][0]["direction"] == "outbound"
    if subject:
        assert conversation["subject"] == subject
    else:
        assert "subject" not in conversation


def test_seed_is_copied_and_never_modified(tmp_path: Path) -> None:
    world = channel_world(tmp_path, "sms")
    seed_path = tmp_path / "sms.json"
    seed_before = json.loads(seed_path.read_text(encoding="utf-8"))

    world.reply_to_conversation("sms-conversation-casey", "See you then.")

    assert json.loads(seed_path.read_text(encoding="utf-8")) == seed_before


def test_outbound_messages_are_recorded_in_event_log(tmp_path: Path) -> None:
    world = channel_world(tmp_path, "sms")

    world.reply_to_conversation("sms-conversation-casey", "On my way.")

    state = json.loads((tmp_path / "sms-state.json").read_text(encoding="utf-8"))
    assert [event["type"] for event in state["events"]] == ["message.outbound"]
    assert state["events"][0]["channel"] == "sms"


def test_invalid_inputs_are_rejected(tmp_path: Path) -> None:
    world = channel_world(tmp_path, "sms")

    with pytest.raises(ValueError, match="query"):
        world.search_conversations("  ")
    with pytest.raises(ValueError, match="body"):
        world.reply_to_conversation("sms-conversation-casey", "")
    with pytest.raises(ValueError, match="recipient_address"):
        world.send_message("sms", "", "Hello")
    with pytest.raises(ValueError, match="must contain @"):
        world.send_message("email", "not-an-address", "Hello")
    with pytest.raises(KeyError, match="conversation not found"):
        world.get_conversation("missing")
    with pytest.raises(ValueError, match="from 1 through 100"):
        world.list_conversations(limit=101)
    with pytest.raises(ValueError, match="channel must be"):
        world.list_conversations(channel="fax")


def test_task_actions_module_is_loaded_and_gates_world_state(tmp_path: Path) -> None:
    actions_path = tmp_path / "actions.py"
    actions_path.write_text(
        textwrap.dedent(
            """
            def mark_done(world, data):
                if world.get("done"):
                    raise ValueError("already done")
                world["done"] = True
                return "task.done", {}

            ACTIONS = {"mark_done": mark_done}
            """
        ),
        encoding="utf-8",
    )

    class OneActionResponder:
        def __init__(self):
            self.feedbacks = []

        def respond(
            self,
            *,
            conversation,
            outbound_message,
            world,
            current_time,
            rejection_feedback=None,
        ):
            self.feedbacks.append(rejection_feedback)
            participant = conversation["participants"][0]
            return {
                "decision": "reply",
                "in_reply_to_message_id": outbound_message["id"],
                "sender": {
                    "display_name": participant["display_name"],
                    "address": participant["address"],
                },
                "body": "Done.",
                "action": {"type": "mark_done", "data": {}},
            }

    responder = OneActionResponder()
    world = channel_world(
        tmp_path, "sms", responder=responder, actions_path=actions_path
    )

    first = world.reply_to_conversation("sms-conversation-casey", "Please finish.")
    assert first["inbound_message"]["body"] == "Done."

    second = world.reply_to_conversation("sms-conversation-casey", "Finish again.")
    assert second["new_inbound_message"] is True
    assert second["inbound_message"]["body"] == "Sorry I can't help you."
    assert responder.feedbacks == [None, None, "already done", "already done"]

    state = json.loads((tmp_path / "sms-state.json").read_text(encoding="utf-8"))
    assert state["world"] == {"done": True}
    event_types = [event["type"] for event in state["events"]]
    assert event_types.count("task.done") == 1
    assert event_types.count("sidecar.response_rejected") == 3
    assert event_types[-1] == "sidecar.fallback_reply"


def test_malformed_responder_output_retries_then_falls_back(tmp_path: Path) -> None:
    """Unparseable model output must retry with feedback, never strand silently.

    Regression for opus r14, where two Fuuffy quote requests each raised
    JSONDecodeError inside the responder and the runtime recorded
    sidecar.failed with no reply delivered.
    """

    class MalformedResponder:
        def __init__(self):
            self.feedbacks = []

        def respond(
            self,
            *,
            conversation,
            outbound_message,
            world,
            current_time,
            rejection_feedback=None,
        ):
            self.feedbacks.append(rejection_feedback)
            json.loads("not json {")  # raises JSONDecodeError like sidecar parsing

    responder = MalformedResponder()
    world = channel_world(tmp_path, "sms", responder=responder)

    result = world.reply_to_conversation("sms-conversation-casey", "Hello?")

    assert result["new_inbound_message"] is True
    assert result["inbound_message"]["body"] == "Sorry I can't help you."
    assert len(responder.feedbacks) == 3
    assert responder.feedbacks[0] is None
    assert all(feedback for feedback in responder.feedbacks[1:])
    state = json.loads((tmp_path / "sms-state.json").read_text(encoding="utf-8"))
    event_types = [event["type"] for event in state["events"]]
    assert event_types.count("sidecar.response_rejected") == 3
    assert "sidecar.failed" not in event_types
    assert event_types[-1] == "sidecar.fallback_reply"


def test_provider_failure_still_fails_without_fallback(tmp_path: Path) -> None:
    class BrokenProviderResponder:
        def respond(
            self,
            *,
            conversation,
            outbound_message,
            world,
            current_time,
            rejection_feedback=None,
        ):
            raise RuntimeError("api connection reset")

    world = channel_world(tmp_path, "sms", responder=BrokenProviderResponder())

    result = world.reply_to_conversation("sms-conversation-casey", "Hello?")

    assert result["new_inbound_message"] is False
    state = json.loads((tmp_path / "sms-state.json").read_text(encoding="utf-8"))
    event_types = [event["type"] for event in state["events"]]
    assert event_types.count("sidecar.failed") == 1
    assert "sidecar.fallback_reply" not in event_types


def test_unregistered_action_is_rejected(tmp_path: Path) -> None:
    class RogueResponder:
        def respond(
            self,
            *,
            conversation,
            outbound_message,
            world,
            current_time,
            rejection_feedback=None,
        ):
            participant = conversation["participants"][0]
            return {
                "decision": "reply",
                "in_reply_to_message_id": outbound_message["id"],
                "sender": {
                    "display_name": participant["display_name"],
                    "address": participant["address"],
                },
                "body": "Trust me.",
                "action": {"type": "grant_admin", "data": {}},
            }

    world = channel_world(tmp_path, "sms", responder=RogueResponder())

    result = world.reply_to_conversation("sms-conversation-casey", "Hello?")

    assert result["new_inbound_message"] is True
    assert result["inbound_message"]["body"] == "Sorry I can't help you."
    state = json.loads((tmp_path / "sms-state.json").read_text(encoding="utf-8"))
    assert state["world"] == {}
    event_types = [event["type"] for event in state["events"]]
    assert event_types.count("sidecar.response_rejected") == 3
    assert event_types[-1] == "sidecar.fallback_reply"
