from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

from primitives.communications import InteractionWorld

ROOT = Path(__file__).parents[1]
TASK = ROOT / "recipes" / "painting-shipping-1-strategy"
SEEDS = TASK / "world" / "communications"


def seeded_world(channel: str, tmp_path: Path) -> InteractionWorld:
    scenario = {
        "schema_version": 1,
        "conversation_seeds": [str(SEEDS / f"{channel}.json")],
    }
    return InteractionWorld(scenario, tmp_path / f"{channel}.json")


def test_strategy_task_registers_both_communication_servers() -> None:
    config = tomllib.loads((TASK / "task.toml").read_text(encoding="utf-8"))

    servers = {
        server["name"]: server for server in config["environment"]["mcp_servers"]
    }

    assert servers == {
        "sms": {
            "name": "sms",
            "transport": "streamable-http",
            "url": "http://sms:8000/mcp",
        },
        "email": {
            "name": "email",
            "transport": "streamable-http",
            "url": "http://email:8000/mcp",
        },
    }


def test_strategy_compose_mounts_task_seeds_read_only() -> None:
    compose = yaml.safe_load(
        (TASK / "environment" / "docker-compose.yaml").read_text(encoding="utf-8")
    )

    assert set(compose["services"]) == {"main", "sms", "email"}
    for channel in ("sms", "email"):
        service = compose["services"][channel]
        assert service["environment"]["COMMUNICATION_CHANNEL"] == channel
        assert service["environment"]["COMMUNICATION_SEED_PATH"] == (
            f"/seed/{channel}.json"
        )
        assert "../world/communications:/seed:ro" in service["volumes"]
        assert "communication-state:/state" in service["volumes"]
        assert service["healthcheck"]


def test_strategy_seeds_are_valid_and_owned_by_addison(tmp_path: Path) -> None:
    for channel in ("sms", "email"):
        store = seeded_world(channel, tmp_path)

        assert store.list_conversations()
        state = store.get_conversation(store.list_conversations()[0]["id"])
        account = next(
            recipient
            for message in state["messages"]
            for recipient in message["recipients"]
            if recipient["address"]
            in {
                "+15555550141",
                "addison.kasper@ymail.com",
            }
        )
        assert account["display_name"] == "Addison Kasper"


def test_strategy_sms_is_fishing_and_email_is_sothebys(tmp_path: Path) -> None:
    sms = seeded_world("sms", tmp_path)
    email = seeded_world("email", tmp_path)

    assert sms.search_conversations("fishing")
    assert email.search_conversations("Sotheby's")
