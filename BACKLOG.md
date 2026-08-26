# Backlog Ideas

## General
- Allow me to integration test the sidecar agent's responses

## Verifier Improvements

- **Verify agent efficiency, not just outcomes.** There are diminishing returns to
  requesting more quotes once a general minimum is established from hourly rate plus
  carrier fee; the verifier should catch pointless extra outreach.

- **Verifier based on exact savings achieved** Requires having each type of company always use a deterministic lowest price for the band. 
Plus need to capture cost of restretching a canvas.

- **Accuracy verifier should be deterministic** Use the world view DB to confirm one payment made to the winning vendor and shipping confirmation recieved.

## Speed
- **Parallelize the three agentic judges** Verification is ~25% of trial wall-clock (10 of 40 min on opus r14) because the strategy/thoroughness/accuracy judges run near-sequentially; rewardkit's agent-judge concurrency defaults to 2. Run all three concurrently (CLI flag/env var if exposed, else upstream tweak) to roughly halve verification.

- **Bundle dependencies into the images** Every verification re-downloads harbor-rewardkit's 56 packages via uvx (~1 min/trial) — pre-warm in the tests Dockerfile. Same for the agent CLIs: bake pinned claude-code/codex into the environment image so harbor's version check skips the per-trial installer download, which was also the source of every AgentSetupTimeoutError.

## Task Expansion
- **Generalize the logistical scenarios beyond painting example** 
Outcome-oriented tasks where the economical solution requires reframing the object, movement method, or responsibility model
Possible variations:
* furniture disassembled, a vehicle driven versus shipped, machinery partially broken down, fragile goods consolidated with another shipment.
 The transferable behavior is establishing the materially different strategies first, then researching providers within the ones worth pursuing.

- **Support agent filling out PDF authorization forms**
Agent should take care of forms for the user but let the user know before agreeing to any signifcant terms.

## World Realism 
- **Incorporate real-time shipping carrier quoting tools** 
Retrieve real package-shipping quotes from major carriers to keep eval up to date. Base reshipper quotes as margin % added on top. 
Keeps hardcoded values more grounded in current costs.

- **Dynamically update task dates and times** 
Part of a logistical challenge is accomplishing the job quickly. For the painting example Sotheby's effectively fines buyers who don't pick up within 30 days. 
The agent interprets the current task as already being penalized because of historical dates. 

- **Improve currency consistency**
 Audit snowflake instructions for Sotheby's to quotes using `comparison_usd`.