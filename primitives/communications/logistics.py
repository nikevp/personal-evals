"""Logistics quote generation and enforcement for the communications sidecar.

This module is task-selected, not built in: a task mounts it by setting
``SIDECAR_EXTENSION_PATH``, the same way ``WORLD_ACTIONS_PATH`` supplies the
action vocabulary. The ``create_extension`` factory reads the task's quote
configuration from the environment and returns the extension, or ``None`` when
the task configures no quote ranges.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any


class QuoteExtension:
    """Generate hidden per-category quote amounts and render them into replies.

    The model never sees the generated amounts: it categorizes the vendor and
    writes the literal ``{amount}`` placeholder in its reply; this middleware
    deterministically renders the category's amount into the body and action.
    """

    AMOUNT_PLACEHOLDER = "{amount}"

    def __init__(
        self,
        quote_ranges_path: str | Path,
        *,
        rng: Any | None = None,
    ) -> None:
        self.quote_ranges = self._load_quote_ranges(quote_ranges_path)
        self.rng = rng if rng is not None else random.Random(0)
        self.candidates: dict[str, dict[str, Any]] = {}

    def prompt_sections(self) -> dict[str, str]:
        self.candidates = {}
        categories = {}
        for category, config in self.quote_ranges.items():
            amount = self.rng.randint(config["minimum"], config["maximum"])
            currency = config["currency"]
            self.candidates[category] = {
                "label": config.get("label", category),
                "currency": currency,
                "amount": amount,
                "formatted_amount": f"{currency} {amount:,}",
            }
            categories[category] = {
                "label": config.get("label", category),
                "currency": currency,
            }
        return {
            "Vendor quote categories": (
                "```json\n"
                + json.dumps(categories, indent=2, ensure_ascii=False)
                + "\n```\n\n"
                "When a vendor in one of these categories submits a quote, do not "
                "choose or invent a number. Write the literal placeholder "
                "{amount} wherever the quoted amount appears in the reply body, "
                "and return `quote_submitted` with the matching "
                "`vendor_category`. The runtime replaces {amount} with the "
                "category's generated amount."
            )
        }

    def post_process(self, response: dict[str, Any]) -> dict[str, Any]:
        action = response.get("action")
        if not isinstance(action, dict) or action.get("type") != "quote_submitted":
            return response
        data = action.get("data")
        if not isinstance(data, dict):
            return response
        vendor_category = data.get("vendor_category")
        if not isinstance(vendor_category, str):
            return response
        candidate = self.candidates.get(vendor_category)
        if candidate is None:
            return response

        expected_amount = candidate["formatted_amount"]
        supplied_amount = data.get("amount")
        data["amount"] = expected_amount
        data["amount_value"] = candidate["amount"]
        data["currency"] = candidate["currency"]

        body = response.get("body")
        if isinstance(body, str):
            rendered = body.replace(self.AMOUNT_PLACEHOLDER, expected_amount)
            if (
                isinstance(supplied_amount, str)
                and supplied_amount
                and supplied_amount not in (expected_amount, self.AMOUNT_PLACEHOLDER)
            ):
                rendered = rendered.replace(supplied_amount, expected_amount)
            response["body"] = rendered
        return response

    @staticmethod
    def _load_quote_ranges(
        quote_ranges_path: str | Path,
    ) -> dict[str, dict[str, Any]]:
        document = json.loads(Path(quote_ranges_path).read_text(encoding="utf-8"))
        if document.get("schema_version") != 1:
            raise ValueError("quote ranges must use schema_version 1")
        categories = document.get("categories")
        if not isinstance(categories, dict) or not categories:
            raise ValueError("quote ranges must define at least one category")
        for category, config in categories.items():
            if not isinstance(category, str) or not category.strip():
                raise ValueError("quote range category names must not be empty")
            if not isinstance(config, dict):
                raise TypeError("each quote range must be an object")
            minimum = config.get("minimum")
            maximum = config.get("maximum")
            if (
                not isinstance(minimum, int)
                or isinstance(minimum, bool)
                or not isinstance(maximum, int)
                or isinstance(maximum, bool)
                or minimum < 0
                or maximum < minimum
            ):
                raise ValueError(
                    f"invalid integer quote range for category {category!r}"
                )
            currency = config.get("currency")
            if not isinstance(currency, str) or not currency.strip():
                raise ValueError(f"quote range {category!r} requires a currency")
        return categories


def create_extension() -> QuoteExtension | None:
    quote_ranges_path = os.environ.get("SIDECAR_QUOTE_RANGES_PATH")
    if not quote_ranges_path:
        return None
    seed = int(os.environ.get("SIDECAR_QUOTE_SEED", "0"))
    return QuoteExtension(quote_ranges_path, rng=random.Random(seed))
