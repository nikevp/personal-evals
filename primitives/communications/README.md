# Communications primitive

Stateful, seedable SMS and email accounts for Harbor tasks. One runtime serves two
deployment modes; every scenario fact — seeds, personas, sidecar context, action
vocabulary — lives in the owning task's `world/` folder, never in this primitive.

## Agent tools

Each server gives the task agent five tools: `list_conversations`,
`search_conversations`, `get_conversation`, `reply_to_conversation`, and
`send_message`. Write tools return the persisted outbound message plus any
immediately available inbound response from a simulated participant.

## Modes

**Per-channel mode** — set `COMMUNICATION_CHANNEL=sms` or `email`. The server hosts
one account initialized from `COMMUNICATION_SEED_PATH` (schema-version-1 seed with
`channel`, `account`, `conversations`), keeping mutable state at
`COMMUNICATION_STATE_PATH` (default `/state/<channel>.json`). Run one service per
channel and mount task seeds read-only. Without a sidecar, outbound messages get no
simulated response.

**Combined mode** — omit `COMMUNICATION_CHANNEL`. The server hosts both channels
over one world defined by `WORLD_SCENARIO_PATH` (schema-version-1 scenario with
`conversation_seeds`, initial hidden `world` state, and a starting `clock`), keeping
state at `WORLD_STATE_PATH`. Tools take an optional `channel` argument.

## Simulated participants (sidecar)

Set `SIDECAR_CONTEXT_PATH` to enable a hidden model-backed responder. After every
outbound message the runtime makes one isolated model call with the task's context
document, the persisted conversation, the latest outbound message, and the current
hidden world state. The model returns a natural-language reply plus one structured
semantic action matching `sidecar-response.schema.json`.

The runtime — not the model — applies world-state transitions. A task registers its
action vocabulary by mounting a Python module and setting `WORLD_ACTIONS_PATH`. The
module defines `ACTIONS`, a dict mapping action names to
`handler(world, data) -> (event_type, event_data)` callables that raise `ValueError`
for invalid transitions. Rejected transitions leave state untouched and are recorded
in the append-only event log. Only the built-in `none` action exists without a task
module.

A rejected response is not dropped silently: the runtime re-invokes the sidecar
with the rejection reason (up to two retries), and if every attempt is rejected it
delivers a fixed safe reply so an engaged participant never goes mute. A sidecar
`no_reply` decision is honored as deliberate silence.

Task-specific behavior beyond the action vocabulary plugs in through
`SIDECAR_EXTENSION_PATH`: a module whose `create_extension()` factory returns an
object that may add prompt sections and post-process replies. The bundled
`logistics.py` extension generates one integer quote candidate inside each
category's inclusive range from `SIDECAR_QUOTE_RANGES_PATH`. The model never sees
the generated amounts: it categorizes the vendor and writes the literal `{amount}`
placeholder, and the extension renders the category's amount into the reply body
and `quote_submitted` data (exposing `amount`, `amount_value`, and `currency` to
the task's action handler).
Candidates are drawn from a deterministic generator seeded by `SIDECAR_QUOTE_SEED`
(default `0`), so a rerun with the same seed produces the same quote sequence; vary
the seed per attempt to vary prices within the ranges.

Sidecar environment: `ANTHROPIC_API_KEY`, `SIDECAR_CONTEXT_PATH`, `SIDECAR_MODEL`
(default `claude-sonnet-4-6`), and optionally `SIDECAR_SCHEMA_PATH`,
`SIDECAR_EXTENSION_PATH`, `SIDECAR_QUOTE_RANGES_PATH`, `SIDECAR_QUOTE_SEED`,
`WORLD_ACTIONS_PATH`.

The model has no persistent session; continuity comes entirely from the JSON state
owned by this service. Never share mutable state between attempts, prompt variants,
or tasks — mount a fresh attempt-scoped volume at `/state`.

## Inspect a seed

`inspect_seed.py` prints a seed's exact start state (account, participants,
conversations, messages) without starting a server or touching runtime state, so a
task author can compare the seed with instructions and grader data before a run:

```bash
python primitives/communications/inspect_seed.py <task>/world/communications/email.json
```
