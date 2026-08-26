# Painting shipping — strategy discovery

Task evaluates whether an agent identifies materially different strategies to get a painting from Hong Kong to Palm Beach. 
A creative solution requires decomposing why the original quote is expensive and identifiying alternatives that are cost effective and safe.

The RewardKit judge reads the final answer from the agent's ATIF trajectory. It uses
three separate criteria. Shipment preparation awards one point each for proposing transport methods: crating, rolling. 
Logistics coverage awards one point each for Carrier Direct, Sotheby's Quote, 3P Reshipper, and Self. 
Grounded feasibility awards one binary point when the answer confirms, or proposes confirming, that Sotheby's can assist with
the rolled option.

Preparation has weight 2 and supplies 50% of the reward. Logistics coverage and
grounded feasibility each have weight 1 and supply 25%. Intermediate searches and tool
results do not earn answer credit.

## Communication tools

The task gives the agent an SMS account and an email account. Both accounts belong to
Addison Kasper. The SMS account starts with one unrelated fishing conversation. The
email account starts with one message from Sotheby's.

The task owns its seed files in `world/communications/`. The services mount these
files as read-only data. Each attempt copies the seeds to a new writable state
volume.

Inspect the exact start state from the repository root:

```bash
python primitives/communications/inspect_seed.py \
  recipes/painting-shipping-1-strategy/world/communications/sms.json
python primitives/communications/inspect_seed.py \
  recipes/painting-shipping-1-strategy/world/communications/email.json
```

Run one attempt from the repository root:

```bash
.venv/bin/harbor job start --env-file .env \
  -p recipes/painting-shipping-1-strategy \
  -a claude-code -m anthropic/claude-sonnet-4-6 --n-attempts 1 \
  --job-name painting-strategy
```
