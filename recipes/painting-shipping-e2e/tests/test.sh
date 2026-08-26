#!/bin/bash
set -euo pipefail

# Extract a compact ground-truth summary so judges can read the authoritative
# world state without the full conversation log crowding it out.
python3 - <<'EOF'
import json
import pathlib

# Harbor re-materializes artifacts at their source paths inside the verifier
# environment, so the communications world state lives at /state/world.json
# there; the local docker re-verify flow mounts the collected trial artifacts,
# which use the destination name instead.
candidates = [
    pathlib.Path("/state/world.json"),
    pathlib.Path("/logs/artifacts/world-state.json"),
]
out = pathlib.Path("/logs/artifacts/world-summary.json")
try:
    src = next(p for p in candidates if p.is_file())
    world = json.loads(src.read_text()).get("world", {})
    summary = {
        "quotes": world.get("quotes"),
        "payment_requests": world.get("payment_requests"),
        "active_payment_request": world.get("active_payment_request"),
        "fulfillment": world.get("fulfillment"),
        "strategy": world.get("strategy"),
    }
    out.write_text(json.dumps(summary, indent=2))
except Exception as exc:  # noqa: BLE001 - judges must still run without a summary
    out.write_text(json.dumps({"error": f"world state unavailable: {exc}"}))
EOF

uvx --from 'harbor-rewardkit==0.1.*' rewardkit /tests \
  --workspace /logs/artifacts
