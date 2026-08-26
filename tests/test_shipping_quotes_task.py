from __future__ import annotations

import csv
import json
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
TASK = ROOT / "recipes" / "painting-shipping-3-quotes"


def test_shipping_quotes_task_registers_communication_servers() -> None:
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


def test_shipping_quotes_task_mounts_read_only_task_owned_seeds() -> None:
    compose = yaml.safe_load(
        (TASK / "environment" / "docker-compose.yaml").read_text(encoding="utf-8")
    )

    for channel in ("sms", "email"):
        service = compose["services"][channel]
        assert service["environment"]["COMMUNICATION_CHANNEL"] == channel
        assert service["environment"]["COMMUNICATION_SEED_PATH"] == (
            f"/seed/{channel}.json"
        )
        assert "../world/communications:/seed:ro" in service["volumes"]
        assert (TASK / "world" / "communications" / f"{channel}.json").is_file()
        assert "communication-state:/state" in service["volumes"]


def test_shipping_quotes_prompt_uses_fixed_vendors_and_requests_recommendation() -> (
    None
):
    prompt = (TASK / "instruction.md").read_text(encoding="utf-8")

    assert "logistics_options.csv" in prompt
    assert "ground_truth" not in prompt
    assert "real companies" not in prompt
    assert "alternative providers" not in prompt
    assert "do not add or replace companies" in prompt
    assert "Contact Method" in prompt
    assert "Contact Details" in prompt
    assert "revised shipping quote" in prompt
    assert "safely de-stretched and rolled" in prompt
    assert "recommend the vendor with the best quote actually received" in prompt
    assert len(prompt.split()) < 350


def test_shipping_quotes_csv_is_copied_into_agent_workspace() -> None:
    dockerfile = (TASK / "environment" / "Dockerfile").read_text(encoding="utf-8")
    csv_path = TASK / "environment" / "logistics_options.csv"

    assert csv_path.is_file()
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header.endswith(",Contact Method,Contact Details")
    assert "WORKDIR /workspace" in dockerfile
    assert ("COPY logistics_options.csv /workspace/logistics_options.csv") in dockerfile
    assert "quote_provider_guide.xlsx" not in dockerfile


def test_shipping_quotes_csv_has_three_real_provider_buckets() -> None:
    csv_path = TASK / "environment" / "logistics_options.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 9
    assert "Mock" not in csv_path.read_text(encoding="utf-8")
    bucket_counts: dict[str, int] = {}
    for row in rows:
        bucket = row["Provider Bucket"]
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    assert bucket_counts == {
        "Sotheby's Packs": 3,
        "Fine-Art Shipper": 3,
        "Task / Errand Service": 3,
    }
    assert any("Zerrand" in row["Logistics Option"] for row in rows)

    contacts = {row["Logistics Option"]: row for row in rows}
    assert (
        contacts["Lightning Errands — Local Pickup Coordination"]["Contact Method"]
        == "SMS"
    )
    assert (
        contacts["Lightning Errands — Local Pickup Coordination"]["Contact Details"]
        == "+852 5555 0101"
    )
    assert (
        contacts["Care Compass — Local Concierge Coordination"]["Contact Method"]
        == "SMS"
    )
    assert (
        contacts["Care Compass — Local Concierge Coordination"]["Contact Details"]
        == "+852 5555 0102"
    )


def test_shipping_quotes_hidden_provider_guide_is_verifier_only() -> None:
    world_guide = TASK / "world" / "quote_provider_guide.xlsx"
    verifier_guide = TASK / "tests" / "quote_provider_guide.xlsx"
    dockerfile = (TASK / "environment" / "Dockerfile").read_text(encoding="utf-8")

    assert world_guide.is_file()
    assert verifier_guide.is_file()
    assert world_guide.read_bytes() == verifier_guide.read_bytes()
    assert "quote_provider_guide.xlsx" not in dockerfile

    rubric = tomllib.loads(
        (TASK / "tests" / "reshipper_contacts.toml").read_text(encoding="utf-8")
    )
    assert "/tests/quote_provider_guide.xlsx" in rubric["judge"]["files"]


def test_shipping_quotes_rubric_prioritizes_recommendation_and_outreach() -> None:
    rubric = tomllib.loads(
        (TASK / "tests" / "reshipper_contacts.toml").read_text(encoding="utf-8")
    )
    criteria = {criterion["name"]: criterion for criterion in rubric["criterion"]}

    assert criteria["verified_contact_and_csv_coverage"]["weight"] == 2.0
    assert criteria["outbound_contact_performed"]["weight"] == 3.0
    assert criteria["best_quote_identified"]["weight"] == 3.0
    assert criteria["sothebys_roll_requote_sent"]["max"] == 3
    assert (
        "Zerrand must remain the least expensive"
        in criteria["best_quote_identified"]["description"]
    )


def test_shipping_quotes_hidden_personas_and_quote_values_are_consistent() -> None:
    sidecar = TASK / "world" / "communications" / "sidecar"
    personas = json.loads((sidecar / "personas.json").read_text(encoding="utf-8"))
    policy = json.loads((sidecar / "policy.json").read_text(encoding="utf-8"))
    context = (sidecar / "context.md").read_text(encoding="utf-8")

    assert personas["schema_version"] == 1
    assert set(personas["persona_definitions"]) == {
        "sothebys_post_sale",
        "fine_art_shipper",
        "task_errand_service",
    }

    participants = {
        participant["organization"]: participant
        for participant in personas["participants"]
    }
    assert participants["Sotheby's"]["quotes"]["rolled"]["native_total"] == (
        "HKD 19,936.25"
    )
    assert participants["Sotheby's"]["quotes"]["crated"]["native_total"] == (
        "HKD 29,150"
    )
    assert participants["Helu-Trans"]["quotes"] == {
        "rolled_usd": 1470,
        "crated_usd": 2020,
    }

    task_totals = {
        company: participants[company]["quotes"]["comparison_usd"]
        for company in ("Zerrand", "Lightning Errands", "Care Compass")
    }
    assert task_totals == {
        "Zerrand": 370,
        "Lightning Errands": 455,
        "Care Compass": 525,
    }
    assert task_totals["Zerrand"] == min(task_totals.values())
    assert "HKD 1,700 partner UPS + RMB 1,080 service fee" in context
    assert policy["reply_policy"]["reply_to_clear_quote_request"] is True
    assert policy["reply_policy"]["channels"] == ["email", "sms"]
    assert participants["Lightning Errands"]["addresses"] == ["+852 5555 0101"]
    assert participants["Care Compass"]["addresses"] == ["+852 5555 0102"]


def test_shipping_quotes_hidden_sidecar_files_are_not_copied_to_agent() -> None:
    dockerfile = (TASK / "environment" / "Dockerfile").read_text(encoding="utf-8")
    compose = (TASK / "environment" / "docker-compose.yaml").read_text(encoding="utf-8")

    assert "world/communications/sidecar" not in dockerfile
    assert "world/communications/sidecar" not in compose
