# Painting shipping quotes — outreach and comparison

This task gives the agent the current shipping strategy and a preloaded CSV quote tracker. The agent uses that tracker to contact Sotheby's and the listed shipping providers, record comparable quotes, and recommend the best quote received. The tracker separates three operating models: Sotheby's packs for a direct carrier, a fine-art shipper packs and manages the shipment, or a Hong Kong task service coordinates local handoffs to a separate qualified packer.

The agent must:

- inspect the existing Sotheby's email thread;
- open `logistics_options.csv`, which is copied into `/workspace` by the task image;
- preserve the three provider buckets and use the listed companies as the available vendor set;
- contact a balanced mix of fine-art shippers and Hong Kong task or errand services;
- use the email or SMS contact already provided for each company;
- send the Sotheby's rolling/re-quote inquiry and provider quote requests;
- update the CSV with outreach status, responses, itemized quotes, exclusions, and next steps;
- select the best reputable quote received, without fabricating missing responses.

The task reuses the strategy task's read-only communication seeds. Every evaluation attempt receives fresh writable communication state, so the verifier can inspect outbound messages without modifying the seed.

The authoritative provider classification, deterministic quote anchors, and response-persona instructions are stored in `world/quote_provider_guide.xlsx`. An identical verifier-only copy lives under `tests/` and is attached to the judge. The agent image copies only the working CSV, so the agent cannot change the judge's reference classification or hidden comparison values.

Sidecar-ready task facts, participant mappings, and response policy live under `world/communications/sidecar/`. They preserve three intentionally different voices: Sotheby's formal procedural response, a Convelio-style fine-art quote response, and a Zerrand-style task-service response. These files are hidden from the task agent. The current communication primitive records outbound messages but does not yet run an outbound-response sidecar, so these instructions guide the verifier and are ready for that future service rather than generating replies on their own.

Run one attempt from the repository root:

```bash
harbor run --env-file .env -p recipes/painting-shipping-3-quotes \
  -a claude-code -m anthropic/claude-opus-5 --n-attempts 1 \
  --job-name painting-shipping-3-quotes
```
