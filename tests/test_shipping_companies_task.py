from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
TASK = ROOT / "recipes" / "painting-shipping-2-companies"


def test_shipping_companies_task_is_research_stage() -> None:
    config = tomllib.loads((TASK / "task.toml").read_text(encoding="utf-8"))

    assert config["task"]["name"] == "logistics/painting-shipping-companies"
    assert config["metadata"]["verifier_stage"] == 2
    assert config["metadata"]["tracking_artifact"] == (
        "prioritized-shipping-company-list"
    )
    assert config["environment"]["mcp_servers"] == [
        {
            "name": "email",
            "transport": "streamable-http",
            "url": "http://email:8000/mcp",
        }
    ]


def test_shipping_companies_task_mounts_read_only_task_owned_seed() -> None:
    compose = yaml.safe_load(
        (TASK / "environment" / "docker-compose.yaml").read_text(encoding="utf-8")
    )
    email = compose["services"]["email"]

    assert email["environment"]["COMMUNICATION_CHANNEL"] == "email"
    assert email["environment"]["COMMUNICATION_SEED_PATH"] == "/seed/email.json"
    assert "../world/communications:/seed:ro" in email["volumes"]
    assert (TASK / "world" / "communications" / "email.json").is_file()
    assert "communication-state:/state" in email["volumes"]


def test_shipping_companies_prompt_covers_both_routes_without_outreach() -> None:
    prompt = (TASK / "instruction.md").read_text(encoding="utf-8")

    assert "de-stretched and rolled canvas" in prompt
    assert "professional flat crate" in prompt
    assert "Do not contact Sotheby's or any shipping company yet" in prompt
    assert "prioritized list" in prompt
    assert "used later to request and compare quotes" in prompt
    assert "CSV" not in prompt
    assert "eval" not in prompt.lower()


def test_shipping_companies_rubric_has_three_simple_criteria() -> None:
    rubric = tomllib.loads(
        (TASK / "tests" / "company_research.toml").read_text(encoding="utf-8")
    )
    criteria = {criterion["name"]: criterion for criterion in rubric["criterion"]}

    assert list(criteria) == [
        "company_list_created",
        "hong_kong_local_options",
        "research_only_no_outbound_contact",
    ]
    assert criteria["company_list_created"]["weight"] == 1.0
    assert criteria["hong_kong_local_options"]["weight"] == 2.0
    assert criteria["hong_kong_local_options"]["max"] == 2
    assert criteria["research_only_no_outbound_contact"]["weight"] == 1.0
