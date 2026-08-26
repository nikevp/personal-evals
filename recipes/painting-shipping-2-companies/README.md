# Painting shipping companies — shortlist research

This is the research stage between shipping-strategy selection and quote collection. It asks the agent to identify and prioritize companies that could fulfill a Hong Kong-to-Palm Beach painting shipment whether the work is ultimately rolled or shipped stretched in a flat crate.

The agent must:

- inspect the existing Sotheby's email thread for shipment context;
- research plausible fine-art shippers, reshippers, task or concierge services, art packers, and managed logistics providers;
- consider both safely rolled and professionally crated-flat routes without assuming either is available;
- provide a useful company list for later quote outreach; and
- make no outbound email, message, quote request, or form submission.

The final answer is the handoff to the later quote-collection task. It should be a prioritized provider list, not a prescribed file format.

The task reuses the strategy task's read-only email seed. Each attempt receives fresh writable communication state so the verifier can confirm that the agent inspected the context without sending anything.

Run one attempt from the repository root:

```bash
harbor run --env-file .env -p recipes/painting-shipping-2-companies \
  -a claude-code -m anthropic/claude-opus-5 --n-attempts 1 \
  --job-name painting-shipping-companies
```

## Issues observed
- No generalization of search. Agent stays focused on fine art shipping companies rather than consider other companies that don't specialize in art. e.g. search for `task services in hong kong`