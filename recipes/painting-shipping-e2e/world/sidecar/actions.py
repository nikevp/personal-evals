"""Sidecar action vocabulary for the end-to-end painting-shipping world.

Loaded by the communications primitive via WORLD_ACTIONS_PATH. Each handler
receives the mutable hidden world state and the sidecar action data, returns
(event_type, event_data), and raises ValueError to reject an invalid transition.
"""

from __future__ import annotations

import copy
from typing import Any


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"action requires {key}")
    return value.strip()


def _state_key(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "_" for character in value.casefold()
    )
    return "_".join(part for part in normalized.split("_") if part)


def strategy_approved(
    world: dict[str, Any], data: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    if world.setdefault("strategy", {}).get("approved"):
        raise ValueError("strategy is already approved")
    route = _required_text(data, "route")
    world["strategy"] = {"approved": True, "route": route}
    return "strategy.approved", {"route": route}


def quote_submitted(
    world: dict[str, Any], data: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    vendor = _required_text(data, "vendor")
    amount = _required_text(data, "amount")
    quote = {"status": "received", "vendor": vendor, "amount": amount}
    comparison_usd = data.get("comparison_usd")
    amount_value = data.get("amount_value")
    if (
        isinstance(amount_value, (int, float))
        and not isinstance(amount_value, bool)
        and data.get("currency") == "USD"
    ):
        comparison_usd = amount_value
    if isinstance(comparison_usd, (int, float)) and not isinstance(
        comparison_usd, bool
    ):
        quote["comparison_usd"] = comparison_usd
    scope = data.get("scope")
    if isinstance(scope, str) and scope.strip():
        quote["scope"] = scope.strip()
    world.setdefault("quotes", {})[_state_key(vendor)] = quote
    return "quote.received", {"vendor": vendor, "amount": amount}


def payment_requested(
    world: dict[str, Any], data: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    vendor = _required_text(data, "vendor")
    quote = world.setdefault("quotes", {}).get(_state_key(vendor))
    if not isinstance(quote, dict) or quote.get("status") != "received":
        raise ValueError("payment request requires a vendor quote")
    reference = _required_text(data, "reference")
    requests = world.setdefault("payment_requests", [])
    for existing in requests:
        # A re-issued invoice reuses its request instead of double-charging.
        if (
            isinstance(existing, dict)
            and existing.get("vendor") == vendor
            and existing.get("reference") == reference
        ):
            return "payment.requested", copy.deepcopy(existing)
    request = {
        "vendor": vendor,
        "amount": _required_text(data, "amount"),
        "purpose": _required_text(data, "purpose"),
        "reference": reference,
        "paid": False,
    }
    requests.append(request)
    fulfillment = world.setdefault("fulfillment", {})
    fulfillment["provider"] = vendor
    fulfillment["status"] = "awaiting_payment"
    return "payment.requested", copy.deepcopy(request)


def payment_confirmed(
    world: dict[str, Any], data: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    requests = world.get("payment_requests") or []
    unpaid = [
        request
        for request in requests
        if isinstance(request, dict) and request.get("paid") is False
    ]
    if not unpaid:
        raise ValueError("there is no unpaid request")
    for request in unpaid:
        request["paid"] = True
    world.setdefault("fulfillment", {})["status"] = "paid"
    return "payment.confirmed", {
        "vendors": [request["vendor"] for request in unpaid],
        "references": [request["reference"] for request in unpaid],
    }


ACTIONS = {
    "strategy_approved": strategy_approved,
    "quote_submitted": quote_submitted,
    "payment_requested": payment_requested,
    "payment_confirmed": payment_confirmed,
}
