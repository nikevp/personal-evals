import copy
import hashlib
import importlib.util
import json
import tomllib
from pathlib import Path
from types import SimpleNamespace

from primitives.communications.logistics import QuoteExtension
from primitives.communications.runtime import InteractionWorld
from primitives.communications.sidecar import SidecarAgent

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipes" / "painting-shipping-e2e"
ACTIONS_PATH = RECIPE / "world" / "sidecar" / "actions.py"


def sidecar_reply(body, action_type="none", **data):
    return {
        "decision": "reply",
        "body": body,
        "action": {"type": action_type, "data": data},
    }


class QueuedSidecar:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def respond(
        self,
        *,
        conversation,
        outbound_message,
        world,
        current_time,
        rejection_feedback=None,
    ):
        self.calls.append(
            {
                "conversation": conversation,
                "outbound_message": outbound_message,
                "world": world,
                "current_time": current_time,
                "rejection_feedback": rejection_feedback,
            }
        )
        response = copy.deepcopy(self.responses.pop(0))
        response["in_reply_to_message_id"] = outbound_message["id"]
        if response["decision"] == "reply":
            participant = conversation["participants"][0]
            response["sender"] = {
                "display_name": participant.get(
                    "display_name", participant.get("organization", "Participant")
                ),
                "address": participant["address"],
                **(
                    {"organization": participant["organization"]}
                    if participant.get("organization")
                    else {}
                ),
            }
        else:
            response["sender"] = None
        return response


def test_task_is_one_uninterrupted_run_and_preserves_user_prompt():
    task_text = (RECIPE / "task.toml").read_text()
    task = tomllib.loads(task_text)
    prompt_bytes = (RECIPE / "instruction.md").read_bytes()
    prompt = prompt_bytes.decode().lower()

    assert "steps" not in task
    assert "[[steps]]" not in task_text
    assert task["task"]["name"] == "logistics/painting-shipping-e2e"
    assert any(
        artifact["source"] == "/logs/agent/trajectory.json"
        for artifact in task["artifacts"]
    )
    assert hashlib.sha256(prompt_bytes).hexdigest() == (
        "94f06c585ab30edc85768e32f48fcf9c9c311e707531843b84f0f3a03e91ea4a"
    )
    assert "end to end" in prompt
    assert "payment" in prompt
    for verifier_hint in (
        "phase 1",
        "phase 2",
        "phase 3",
        "artifact",
        "csv",
        "company quota",
        "verifier",
    ):
        assert verifier_hint not in prompt


def test_verifiers_are_three_simple_rewardkit_dimensions():
    tests_dir = RECIPE / "tests"
    dimensions = {
        "strategy": tests_dir / "strategy/strategy.toml",
        "thoroughness": tests_dir / "thoroughness/thoroughness.toml",
        "accuracy": tests_dir / "accuracy/accuracy.toml",
    }
    criteria_by_dimension = {
        "strategy": ["shipment_packing_alternatives", "logistics_approach_coverage"],
        "thoroughness": [
            "provider_outreach_coverage",
            "sothebys_roll_requote_sent",
            "negotiation",
        ],
        "accuracy": ["selected_quote_real", "shipment_completed", "channel_discipline"],
    }

    assert {
        path.name
        for path in tests_dir.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    } == set(dimensions)

    for name, path in dimensions.items():
        rubric = tomllib.loads(path.read_text())
        assert [
            criterion["name"] for criterion in rubric["criterion"]
        ] == criteria_by_dimension[name]
        assert len(rubric["criterion"]) <= 3
        assert rubric["scoring"] == {"aggregation": "weighted_mean"}
        assert "prompt_template" not in rubric["judge"]
        assert rubric["judge"]["judge"] == "claude-code"
        assert rubric["judge"]["model"] == "claude-sonnet-4-6"
        assert rubric["judge"]["atif-trajectory"] == "/logs/agent/trajectory.json"

    reward = tomllib.loads((tests_dir / "reward.toml").read_text())
    assert reward == {"reward": [{"name": "reward", "aggregation": "weighted_mean"}]}
    assert not list(tests_dir.glob("*.md"))
    assert not list(tests_dir.glob("*.xlsx*"))


def test_single_rewardkit_run_discovers_all_three_dimensions():
    runner = (RECIPE / "tests/test.sh").read_text()
    assert runner.count("rewardkit /tests") == 1
    assert "run_lane" not in runner
    assert "aggregate_rewards" not in runner
    assert "prepare_evidence" not in runner
    assert "[documents]" not in runner


def test_recipe_is_self_contained_except_for_communications_primitive():
    compose = (RECIPE / "environment/docker-compose.yaml").read_text()
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())

    assert "../../../primitives/communications" in compose
    assert "../world:/scenario:ro" in compose
    assert "../.." not in compose.replace("../../../primitives/communications", "")
    assert scenario["conversation_seeds"] == [
        "/scenario/email.json",
        "/scenario/user-sms.json",
    ]
    assert "participant_seeds" not in scenario
    assert scenario["world"]["payment_requests"] == []
    assert "payments" not in scenario["world"]
    assert (RECIPE / "world/email.json").is_file()
    assert (RECIPE / "world/user-sms.json").is_file()
    assert (RECIPE / "world/sidecar/context.md").is_file()
    assert (RECIPE / "world/sidecar/quote-ranges.json").is_file()
    assert (RECIPE / "world/sidecar/actions.py").is_file()
    assert not (RECIPE / "world/sidecar/participants.json").exists()
    assert not (RECIPE / "world/sidecar/policy.json").exists()
    assert "SIDECAR_CONTEXT_PATH: /scenario/sidecar/context.md" in compose
    assert "SIDECAR_EXTENSION_PATH: /app/logistics.py" in compose
    assert "SIDECAR_MODEL:" in compose
    assert "SIDECAR_QUOTE_RANGES_PATH: /scenario/sidecar/quote-ranges.json" in compose
    assert "WORLD_ACTIONS_PATH: /scenario/sidecar/actions.py" in compose

    main_service = compose.split("  communications:", maxsplit=1)[0]
    assert "/scenario" not in main_service
    assert "/state" not in main_service


def test_hidden_seed_loads_starting_email_and_model_sidecar_context(tmp_path):
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())
    scenario["conversation_seeds"] = [
        str(RECIPE / "world/email.json"),
        str(RECIPE / "world/user-sms.json"),
    ]
    local_scenario = tmp_path / "scenario.json"
    local_scenario.write_text(json.dumps(scenario))

    state_path = tmp_path / "world.json"
    InteractionWorld(local_scenario, state_path, actions_path=ACTIONS_PATH)
    state = json.loads(state_path.read_text())

    conversation = next(
        item
        for item in state["conversations"]
        if item["id"] == "email-conversation-sothebys-hk1740"
    )
    assert any(
        "HKD 29,150.00" in message["body"] for message in conversation["messages"]
    )
    assert "participant_profiles" not in state
    assert "simulated_participants" not in state

    sidecar = QueuedSidecar(
        sidecar_reply(
            "Yes, let's use the qualified rolled route.",
            "strategy_approved",
            route="qualified rolled route",
        ),
        sidecar_reply(
            "The strategy is already approved. Continue until payment is needed."
        ),
    )
    world = InteractionWorld(
        local_scenario, state_path, responder=sidecar, actions_path=ACTIONS_PATH
    )
    approval = world.reply_to_conversation(
        "sms-conversation-addison",
        "I recommend the qualified rolled route.",
    )
    assert "qualified rolled route" in approval["inbound_message"]["body"]

    result = world.reply_to_conversation(
        "sms-conversation-addison",
        "Want me to proceed with the direct route?",
    )
    assert result["new_inbound_message"] is True
    assert "already approved" in result["inbound_message"]["body"]
    assert sidecar.calls[1]["world"]["strategy"]["approved"] is True


def test_sothebys_deframing_quote_supports_payment_path(tmp_path):
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())
    scenario["conversation_seeds"] = [
        str(RECIPE / "world/email.json"),
        str(RECIPE / "world/user-sms.json"),
    ]
    local_scenario = tmp_path / "scenario.json"
    local_scenario.write_text(json.dumps(scenario))
    state_path = tmp_path / "world.json"
    sidecar = QueuedSidecar(
        sidecar_reply(
            "Unframing and rolling alone is HKD 1,500.",
            "quote_submitted",
            vendor="Sotheby's",
            amount="HKD 1,500",
            comparison_usd=192,
            scope="unframing and rolling only",
        ),
        sidecar_reply(
            "Please pay reference 62840177 for HKD 1,500.",
            "payment_requested",
            vendor="Sotheby's",
            amount="HKD 1,500",
            purpose="unframing and rolling only",
            reference="62840177",
        ),
    )
    world = InteractionWorld(
        local_scenario, state_path, responder=sidecar, actions_path=ACTIONS_PATH
    )

    quote = world.reply_to_conversation(
        "email-conversation-sothebys-hk1740",
        "How much for just the unframing and rolling, without shipping?",
    )
    assert "HKD 1,500" in quote["inbound_message"]["body"]

    invoice = world.reply_to_conversation(
        "email-conversation-sothebys-hk1740",
        "Please proceed with the de-framing only.",
    )
    assert "62840177" in invoice["inbound_message"]["body"]

    state = json.loads(state_path.read_text())
    assert state["world"]["quotes"]["sotheby_s"] == {
        "status": "received",
        "vendor": "Sotheby's",
        "amount": "HKD 1,500",
        "comparison_usd": 192,
        "scope": "unframing and rolling only",
    }
    assert state["world"]["payment_requests"] == [{
        "vendor": "Sotheby's",
        "amount": "HKD 1,500",
        "purpose": "unframing and rolling only",
        "reference": "62840177",
        "paid": False,
    }]
    event_types = [event["type"] for event in state["events"]]
    assert "sidecar.response_rejected" not in event_types


def test_hidden_seed_can_complete_helu_payment_path(tmp_path):
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())
    scenario["conversation_seeds"] = [
        str(RECIPE / "world/email.json"),
        str(RECIPE / "world/user-sms.json"),
    ]
    local_scenario = tmp_path / "scenario.json"
    local_scenario.write_text(json.dumps(scenario))
    state_path = tmp_path / "world.json"
    sidecar = QueuedSidecar(
        sidecar_reply(
            "Yes, let's use the qualified rolled route.",
            "strategy_approved",
            route="qualified rolled route",
        ),
        sidecar_reply(
            "An emailed approval naming the designated collecting company and two"
            " working days' notice are required.",
            "quote_submitted",
            vendor="Sotheby's",
            amount="HKD 19,936.25",
            comparison_usd=2555,
            scope="managed rolled route",
        ),
        sidecar_reply(
            "Our qualified rolled-route quote is USD 1,470.",
            "quote_submitted",
            vendor="Helu-Trans",
            amount="USD 1,470",
            comparison_usd=1470,
            scope="qualified rolled-route shipping service",
        ),
        sidecar_reply(
            "Please pay invoice HT-1470 for USD 1,470.",
            "payment_requested",
            vendor="Helu-Trans",
            amount="USD 1,470",
            purpose="qualified rolled-route shipping service",
            reference="HT-1470",
        ),
        sidecar_reply(
            "I paid the pending request. Please confirm with the selected vendor.",
            "payment_confirmed",
        ),
        sidecar_reply(
            "Payment confirmed. We will proceed with the selected service.",
        ),
    )
    world = InteractionWorld(
        local_scenario, state_path, responder=sidecar, actions_path=ACTIONS_PATH
    )

    world.reply_to_conversation(
        "sms-conversation-addison",
        "I recommend the qualified rolled route.",
    )
    release = world.reply_to_conversation(
        "email-conversation-sothebys-hk1740",
        "What do you need from me to release the painting to a third party?",
    )
    assert "emailed approval" in release["inbound_message"]["body"]

    quote = world.send_message(
        "email",
        "kellyfung@helutrans.com",
        "Please provide a quote for the rolled route.",
    )
    helu_conversation = quote["conversation_id"]
    assert "USD 1,470" in quote["inbound_message"]["body"]

    invoice = world.reply_to_conversation(
        helu_conversation,
        "Please proceed with the selected option.",
    )
    assert "invoice HT-1470" in invoice["inbound_message"]["body"]

    payment = world.reply_to_conversation(
        "sms-conversation-addison",
        "Please pay the pending request.",
    )
    assert payment["inbound_message"]["body"].startswith("I paid the pending request")
    acknowledgment = world.reply_to_conversation(
        helu_conversation,
        "The owner paid invoice HT-1470; please proceed.",
    )
    assert "Payment confirmed" in acknowledgment["inbound_message"]["body"]

    state = json.loads(state_path.read_text())
    assert state["world"]["fulfillment"] == {
        "provider": "Helu-Trans",
        "status": "paid",
    }
    assert state["world"]["payment_requests"] == [{
        "vendor": "Helu-Trans",
        "amount": "USD 1,470",
        "purpose": "qualified rolled-route shipping service",
        "reference": "HT-1470",
        "paid": True,
    }]


def test_two_sequential_payment_requests_complete_without_conflict(tmp_path):
    """A vendor can invoice an initial payment and later a final payment.

    Both request/confirm cycles must complete with no overlap: confirming the
    first request must not block or pre-pay the second.
    """
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())
    scenario["conversation_seeds"] = [
        str(RECIPE / "world/email.json"),
        str(RECIPE / "world/user-sms.json"),
    ]
    local_scenario = tmp_path / "scenario.json"
    local_scenario.write_text(json.dumps(scenario))
    state_path = tmp_path / "world.json"
    sidecar = QueuedSidecar(
        sidecar_reply(
            "Our qualified rolled-route quote is USD 1,470.",
            "quote_submitted",
            vendor="Helu-Trans",
            amount="USD 1,470",
            comparison_usd=1470,
            scope="qualified rolled-route shipping service",
        ),
        sidecar_reply(
            "Please pay the deposit invoice HT-DEP for USD 500.",
            "payment_requested",
            vendor="Helu-Trans",
            amount="USD 500",
            purpose="booking deposit",
            reference="HT-DEP",
        ),
        sidecar_reply(
            "I paid the pending request. Please confirm with the vendor.",
            "payment_confirmed",
        ),
        sidecar_reply(
            "Deposit received. The final balance invoice HT-FIN is USD 970.",
            "payment_requested",
            vendor="Helu-Trans",
            amount="USD 970",
            purpose="final balance",
            reference="HT-FIN",
        ),
        sidecar_reply(
            "I paid the pending request. Please confirm with the vendor.",
            "payment_confirmed",
        ),
        sidecar_reply(
            "All payments received. Collection is being scheduled.",
        ),
    )
    world = InteractionWorld(
        local_scenario, state_path, responder=sidecar, actions_path=ACTIONS_PATH
    )

    quote = world.send_message(
        "email", "kellyfung@helutrans.com", "Please quote the rolled route."
    )
    helu_conversation = quote["conversation_id"]

    deposit = world.reply_to_conversation(
        helu_conversation, "Please proceed and send your deposit invoice."
    )
    assert "HT-DEP" in deposit["inbound_message"]["body"]

    world.reply_to_conversation(
        "sms-conversation-addison", "Please pay the deposit invoice."
    )
    mid_state = json.loads(state_path.read_text())
    assert [request["paid"] for request in mid_state["world"]["payment_requests"]] == [
        True
    ]

    final_invoice = world.reply_to_conversation(
        helu_conversation, "Deposit paid. Please continue."
    )
    assert "HT-FIN" in final_invoice["inbound_message"]["body"]

    world.reply_to_conversation(
        "sms-conversation-addison", "Please pay the final invoice."
    )
    acknowledgment = world.reply_to_conversation(
        helu_conversation, "Final invoice paid; please confirm."
    )
    assert "payments received" in acknowledgment["inbound_message"]["body"]

    state = json.loads(state_path.read_text())
    requests = state["world"]["payment_requests"]
    assert [request["reference"] for request in requests] == ["HT-DEP", "HT-FIN"]
    assert [request["paid"] for request in requests] == [True, True]
    assert state["world"]["fulfillment"] == {
        "provider": "Helu-Trans",
        "status": "paid",
    }
    event_types = [event["type"] for event in state["events"]]
    assert event_types.count("payment.requested") == 2
    assert event_types.count("payment.confirmed") == 2
    assert "sidecar.response_rejected" not in event_types


def test_reissued_invoice_with_same_reference_is_idempotent(tmp_path):
    """Re-sending the same invoice must not create a second payable request.

    Regression for sol r16, where Zetter re-issued its USD 412 invoice and the
    owner's confirm-all paid the duplicate too, double-charging in ground truth.
    """
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())
    scenario["conversation_seeds"] = [
        str(RECIPE / "world/email.json"),
        str(RECIPE / "world/user-sms.json"),
    ]
    local_scenario = tmp_path / "scenario.json"
    local_scenario.write_text(json.dumps(scenario))
    state_path = tmp_path / "world.json"
    invoice_reply = sidecar_reply(
        "Please pay invoice ZT-412 for USD 412.",
        "payment_requested",
        vendor="Zetter Picture Framer",
        amount="USD 412",
        purpose="onsite de-stretching, packing, and carrier handover",
        reference="ZT-412",
    )
    sidecar = QueuedSidecar(
        sidecar_reply(
            "Our onsite service is USD 412.",
            "quote_submitted",
            vendor="Zetter Picture Framer",
            amount="USD 412",
            comparison_usd=412,
            scope="onsite de-stretching, packing, and carrier handover",
        ),
        invoice_reply,
        copy.deepcopy(invoice_reply),
        sidecar_reply(
            "I paid the pending request. Please confirm with the vendor.",
            "payment_confirmed",
        ),
    )
    world = InteractionWorld(
        local_scenario, state_path, responder=sidecar, actions_path=ACTIONS_PATH
    )

    quote = world.send_message(
        "email", "info@zetterframing.com.hk", "Please quote onsite packing."
    )
    conversation = quote["conversation_id"]
    world.reply_to_conversation(conversation, "Please send your invoice.")
    reissue = world.reply_to_conversation(
        conversation, "Could you resend the invoice? I did not receive it."
    )
    assert "ZT-412" in reissue["inbound_message"]["body"]

    world.reply_to_conversation(
        "sms-conversation-addison", "Please pay the pending invoice."
    )

    state = json.loads(state_path.read_text())
    requests = state["world"]["payment_requests"]
    assert len(requests) == 1
    assert requests[0]["reference"] == "ZT-412"
    assert requests[0]["paid"] is True
    event_types = [event["type"] for event in state["events"]]
    assert event_types.count("payment.requested") == 2
    assert event_types.count("payment.confirmed") == 1


def test_zerrand_uses_one_consolidated_payment_request(tmp_path):
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())
    scenario["conversation_seeds"] = [
        str(RECIPE / "world/email.json"),
        str(RECIPE / "world/user-sms.json"),
    ]
    local_scenario = tmp_path / "scenario.json"
    local_scenario.write_text(json.dumps(scenario))
    state_path = tmp_path / "world.json"
    sidecar = QueuedSidecar(
        sidecar_reply(
            "The combined quote is approximately USD 370.",
            "quote_submitted",
            vendor="Zerrand",
            amount="RMB 1,080 + HKD 1,700",
            comparison_usd=370,
            scope="collection coordination and partner UPS shipment",
        ),
        sidecar_reply(
            "Please pay the consolidated request ZR-370 for USD 370.",
            "payment_requested",
            vendor="Zerrand",
            amount="USD 370",
            purpose="combined collection coordination and UPS shipping",
            reference="ZR-370",
        ),
        sidecar_reply(
            "I paid the pending request. Please confirm with the selected vendor.",
            "payment_confirmed",
        ),
        sidecar_reply(
            "Payment confirmed. We will proceed with the combined service.",
        ),
    )
    world = InteractionWorld(
        local_scenario, state_path, responder=sidecar, actions_path=ACTIONS_PATH
    )

    quote = world.send_message(
        "email",
        "contact@zerrand.com",
        "Please provide a quote for the rolled route.",
    )
    zerrand_conversation = quote["conversation_id"]
    payment_request = world.reply_to_conversation(
        zerrand_conversation,
        "You are the selected vendor; please proceed.",
    )
    assert "ZR-370" in payment_request["inbound_message"]["body"]

    first_state = json.loads(state_path.read_text())
    assert first_state["world"]["payment_requests"] == [{
        "vendor": "Zerrand",
        "amount": "USD 370",
        "purpose": "combined collection coordination and UPS shipping",
        "reference": "ZR-370",
        "paid": False,
    }]

    world.reply_to_conversation(
        "sms-conversation-addison",
        "Please pay the pending request.",
    )
    acknowledgment = world.reply_to_conversation(
        zerrand_conversation,
        "The pending request was paid; please proceed.",
    )
    assert "Payment confirmed" in acknowledgment["inbound_message"]["body"]

    final_state = json.loads(state_path.read_text())
    assert final_state["world"]["payment_requests"][0]["paid"] is True
    assert final_state["world"]["fulfillment"] == {
        "provider": "Zerrand",
        "status": "paid",
    }
    event_types = [event["type"] for event in final_state["events"]]
    assert event_types.count("payment.requested") == 1
    assert event_types.count("payment.confirmed") == 1


def test_agent_image_has_no_seeded_vendor_csv():
    dockerfile = (RECIPE / "environment/Dockerfile").read_text()
    assert "logistics_options" not in dockerfile
    assert not (RECIPE / "environment/logistics_options.csv").exists()


def test_sidecar_context_captures_personas_quote_categories_and_payment_rules():
    context = (RECIPE / "world/sidecar/context.md").read_text()

    for participant in (
        "Addison Kasper",
        "Sotheby's Post Sale Services",
        "Helu-Trans Hong Kong",
        "Lotus Fine Arts",
        "Premier International Movers",
        "Zerrand",
        "Mail Boxes Etc. Hong Kong",
        "DHL",
        "FedEx",
    ):
        assert participant in context
    assert "fine_art_third_party" in context
    assert "task_errand_service" in context
    assert "shipping_carrier" in context
    assert "restretching_service" in context
    assert "Logistics platform behavior" in context
    for platform in ("FreightAmigo", "Easyship", "Fuuffy"):
        assert platform in context
    for restretcher in ("All Art Installation", "ArtWorks of Northwood"):
        assert restretcher in context
    assert "DHL-QUOTE" in context
    assert "FEDEX-QUOTE" in context
    assert "{amount}" in context
    assert "runtime-generated candidate" not in context
    assert "HKD 1,500" in context
    assert "forgiven" in context
    assert "HT-QUOTE" in context
    assert "LF-QUOTE" in context
    assert "PM-QUOTE" in context
    assert "ZR-QUOTE" in context
    assert "payment_confirmed" in context
    assert "unpaid request" in context
    assert "safety_confirmed" not in context
    assert "shipment_delivered" not in context
    assert "payment_stages" not in context
    assert "infer whether it belongs to a category" in context
    assert "the complete list" in context
    assert "no_reply" in context
    assert "plausible vendor" not in context


def test_sidecar_model_call_is_isolated_and_receives_current_context(tmp_path):
    context_path = tmp_path / "context.md"
    context_path.write_text("Hidden participant facts")
    schema_path = ROOT / "primitives/communications/sidecar-response.schema.json"
    model_response = {
        "decision": "no_reply",
        "in_reply_to_message_id": "email-msg-1",
        "sender": None,
        "body": None,
        "action": {"type": "none", "data": {}},
    }

    class FakeMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(model_response))]
            )

    messages = FakeMessages()
    client = SimpleNamespace(messages=messages)

    class MaximumRng:
        def __init__(self):
            self.calls = []

        def randint(self, minimum, maximum):
            self.calls.append((minimum, maximum))
            return maximum

    rng = MaximumRng()
    sidecar = SidecarAgent(
        context_path,
        schema_path,
        model="test-model",
        extension=QuoteExtension(RECIPE / "world/sidecar/quote-ranges.json", rng=rng),
        client=client,
    )
    result = sidecar.respond(
        conversation={
            "id": "thread-1",
            "participants": [
                {
                    "display_name": "Unknown Vendor",
                    "organization": "Unknown Vendor LLC",
                    "address": "hello@unknown.example",
                }
            ],
            "messages": [{"body": "hello"}],
        },
        outbound_message={"id": "email-msg-1", "body": "hello"},
        world={"active_payment_request": None},
        current_time="2026-08-21T13:00:00+00:00",
    )

    assert result == model_response
    assert len(messages.calls) == 1
    call = messages.calls[0]
    assert call["model"] == "test-model"
    prompt = call["messages"][0]["content"]
    assert "Hidden participant facts" in prompt
    assert "active_payment_request" in prompt
    assert "email-msg-1" in prompt
    assert "Vendor quote categories" in prompt
    assert '"fine_art_third_party"' in prompt
    assert '"task_errand_service"' in prompt
    assert '"shipping_carrier"' in prompt
    assert '"restretching_service"' in prompt
    assert "{amount}" in prompt
    assert "formatted_amount" not in prompt
    assert "USD 3,000" not in prompt
    assert "USD 600" not in prompt
    assert "USD 500" not in prompt
    assert rng.calls == [(1500, 3000), (350, 600), (250, 500), (400, 500)]
    assert "Previous response rejected" not in prompt


def test_unlisted_vendor_quote_ranges_are_inclusive_and_configured_by_category():
    ranges = json.loads((RECIPE / "world/sidecar/quote-ranges.json").read_text())[
        "categories"
    ]

    assert ranges["fine_art_third_party"] == {
        "label": "Fine-art shipping through a third party",
        "currency": "USD",
        "minimum": 1500,
        "maximum": 3000,
    }
    assert ranges["task_errand_service"] == {
        "label": "Task or errand coordination service",
        "currency": "USD",
        "minimum": 350,
        "maximum": 600,
    }
    assert ranges["shipping_carrier"] == {
        "label": "Shipping carrier for the rolled package",
        "currency": "USD",
        "minimum": 250,
        "maximum": 500,
    }
    assert ranges["restretching_service"] == {
        "label": "Canvas re-stretching on delivery",
        "currency": "USD",
        "minimum": 400,
        "maximum": 500,
    }


def test_sidecar_renders_generated_category_amount_in_quote_action_and_body(tmp_path):
    context_path = tmp_path / "context.md"
    context_path.write_text("Category quote test")
    schema_path = ROOT / "primitives/communications/sidecar-response.schema.json"
    model_response = {
        "decision": "reply",
        "in_reply_to_message_id": "email-msg-quote",
        "sender": {
            "display_name": "Example Art Logistics",
            "organization": "Example Art Logistics",
            "address": "quotes@example.test",
        },
        "body": "Our quote is {amount}, revised from our earlier USD 999 estimate.",
        "action": {
            "type": "quote_submitted",
            "data": {
                "vendor": "Example Art Logistics",
                "vendor_category": "fine_art_third_party",
                "amount": "USD 999",
                "scope": "third-party fine-art shipping",
            },
        },
    }

    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(model_response))]
            )

    class MinimumRng:
        def randint(self, minimum, maximum):
            return minimum

    sidecar = SidecarAgent(
        context_path,
        schema_path,
        model="test-model",
        extension=QuoteExtension(
            RECIPE / "world/sidecar/quote-ranges.json", rng=MinimumRng()
        ),
        client=SimpleNamespace(messages=FakeMessages()),
    )
    result = sidecar.respond(
        conversation={
            "id": "thread-quote",
            "participants": [
                {
                    "display_name": "Example Art Logistics",
                    "organization": "Example Art Logistics",
                    "address": "quotes@example.test",
                }
            ],
            "messages": [],
        },
        outbound_message={"id": "email-msg-quote", "body": "Please quote."},
        world={"quotes": {}},
        current_time="2026-08-21T13:00:00+00:00",
    )

    assert result["body"] == (
        "Our quote is USD 1,500, revised from our earlier USD 1,500 estimate."
    )
    assert result["action"]["data"]["amount"] == "USD 1,500"
    assert result["action"]["data"]["amount_value"] == 1500
    assert result["action"]["data"]["currency"] == "USD"

    spec = importlib.util.spec_from_file_location("e2e_actions", ACTIONS_PATH)
    actions_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(actions_module)
    world = {}
    actions_module.ACTIONS["quote_submitted"](world, result["action"]["data"])
    assert world["quotes"]["example_art_logistics"]["comparison_usd"] == 1500


def test_runtime_rejects_payment_confirmation_without_active_request(tmp_path):
    scenario = json.loads((RECIPE / "world/scenario.json").read_text())
    scenario["conversation_seeds"] = [
        str(RECIPE / "world/email.json"),
        str(RECIPE / "world/user-sms.json"),
    ]
    local_scenario = tmp_path / "scenario.json"
    local_scenario.write_text(json.dumps(scenario))
    state_path = tmp_path / "world.json"
    invalid_confirmation = sidecar_reply("I paid the request.", "payment_confirmed")
    sidecar = QueuedSidecar(
        invalid_confirmation, invalid_confirmation, invalid_confirmation
    )
    world = InteractionWorld(
        local_scenario, state_path, responder=sidecar, actions_path=ACTIONS_PATH
    )

    result = world.reply_to_conversation(
        "sms-conversation-addison",
        "Please confirm a payment that no vendor requested.",
    )

    assert result["new_inbound_message"] is True
    assert result["inbound_message"]["body"] == "Sorry I can't help you."
    assert sidecar.calls[0]["rejection_feedback"] is None
    assert "no unpaid request" in sidecar.calls[1]["rejection_feedback"]
    assert "no unpaid request" in sidecar.calls[2]["rejection_feedback"]
    state = json.loads(state_path.read_text())
    assert state["world"]["payment_requests"] == []
    event_types = [event["type"] for event in state["events"]]
    assert event_types.count("sidecar.response_rejected") == 3
    assert event_types[-1] == "sidecar.fallback_reply"
