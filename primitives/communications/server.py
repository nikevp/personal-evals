# /// script
# requires-python = ">=3.12"
# dependencies = ["anthropic>=0.71,<1", "fastmcp==3.4.7"]
# ///
"""MCP entrypoint for the communications primitive.

Two modes share one runtime:

- Per-channel mode (``COMMUNICATION_CHANNEL=sms|email``) serves one seeded
  account, mirroring a plain inbox with no simulated participants unless a
  sidecar is configured.
- Combined mode (no ``COMMUNICATION_CHANNEL``) serves both channels over one
  scenario-defined world, usually with a model-backed sidecar answering
  outbound messages and recording hidden state transitions.
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP
from runtime import InteractionWorld
from sidecar import SidecarAgent, load_extension

CHANNEL = os.environ.get("COMMUNICATION_CHANNEL", "").strip().lower() or None
if CHANNEL is not None and CHANNEL not in {"sms", "email"}:
    raise RuntimeError("COMMUNICATION_CHANNEL must be either 'sms' or 'email'")

context_path = os.environ.get("SIDECAR_CONTEXT_PATH")
extension_path = os.environ.get("SIDECAR_EXTENSION_PATH")
responder = (
    SidecarAgent(
        context_path,
        os.environ.get("SIDECAR_SCHEMA_PATH", "/app/sidecar-response.schema.json"),
        model=os.environ.get("SIDECAR_MODEL", "claude-sonnet-4-6"),
        extension=load_extension(extension_path) if extension_path else None,
    )
    if context_path
    else None
)

if CHANNEL:
    scenario: dict[str, Any] | str = {
        "schema_version": 1,
        "conversation_seeds": [os.environ["COMMUNICATION_SEED_PATH"]],
    }
    state_path = os.environ.get("COMMUNICATION_STATE_PATH", f"/state/{CHANNEL}.json")
else:
    scenario = os.environ.get("WORLD_SCENARIO_PATH", "/scenario/scenario.json")
    state_path = os.environ.get("WORLD_STATE_PATH", "/state/world.json")

world = InteractionWorld(
    scenario,
    state_path,
    responder=responder,
    actions_path=os.environ.get("WORLD_ACTIONS_PATH"),
)
mcp = FastMCP(f"{CHANNEL}-communications" if CHANNEL else "communications")


if CHANNEL:

    @mcp.tool()
    def list_conversations(limit: int = 20) -> list[dict[str, Any]]:
        """View newest-first conversation summaries for this communication account."""
        return world.list_conversations(channel=CHANNEL, limit=limit)

    @mcp.tool()
    def search_conversations(query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search conversation subjects, contacts, addresses, and message contents."""
        return world.search_conversations(query=query, channel=CHANNEL, limit=limit)

    @mcp.tool()
    def get_conversation(conversation_id: str) -> dict[str, Any]:
        """Get a complete conversation by the ID returned from list or search."""
        return world.get_conversation(conversation_id)

    @mcp.tool()
    def reply_to_conversation(conversation_id: str, body: str) -> dict[str, Any]:
        """Send a reply in an existing conversation thread."""
        return world.reply_to_conversation(conversation_id, body)

    @mcp.tool()
    def send_message(
        recipient_address: str,
        body: str,
        subject: str | None = None,
        recipient_name: str | None = None,
        organization: str | None = None,
    ) -> dict[str, Any]:
        """Start a new outbound conversation with a recipient on this channel."""
        return world.send_message(
            CHANNEL,
            recipient_address,
            body,
            subject=subject,
            recipient_name=recipient_name,
            organization=organization,
        )

else:

    @mcp.tool()
    def list_conversations(
        channel: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """List recent email or SMS conversations. Omit channel to list both."""
        return world.list_conversations(channel=channel, limit=limit)

    @mcp.tool()
    def search_conversations(
        query: str, channel: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search email and SMS conversation participants, subjects, and messages."""
        return world.search_conversations(query=query, channel=channel, limit=limit)

    @mcp.tool()
    def get_conversation(conversation_id: str) -> dict[str, Any]:
        """Read a complete email or SMS conversation."""
        return world.get_conversation(conversation_id)

    @mcp.tool()
    def reply_to_conversation(conversation_id: str, body: str) -> dict[str, Any]:
        """Reply in a thread and return any immediately available inbound response."""
        return world.reply_to_conversation(conversation_id, body)

    @mcp.tool()
    def send_message(
        channel: str,
        recipient_address: str,
        body: str,
        subject: str | None = None,
        recipient_name: str | None = None,
        organization: str | None = None,
    ) -> dict[str, Any]:
        """Start a thread and return any immediately available inbound response."""
        return world.send_message(
            channel,
            recipient_address,
            body,
            subject=subject,
            recipient_name=recipient_name,
            organization=organization,
        )


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
