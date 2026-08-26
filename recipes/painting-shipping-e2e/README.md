# Painting shipping — end-to-end single run

This recipe evaluates whether one uninterrupted agent run can successfully ship a painting across the world for less than $3.6k USD.

# The Agent's Context
The agent is only provided with the user's instructions and an initial email thread with Sotheby's. 
The email thread provides critical information on pricing and the paintings physical dimensions. 
The Sotheby's quote is ground truth for the number to beat.


# Evaluation

The final reward is the equal-weight mean of three RewardKit dimensions organized
under `tests/`: strategy, companies, and quotes. Each dimension uses one focused
judge rubric.


# Concerns/Risks

- Agent sending actual communications to companies. Most likely through web forms only requiring a post request.


# Run

Run one Sonnet attempt with:

```bash
.venv/bin/harbor job start --env-file .env \
  -p recipes/painting-shipping-e2e \
  -a claude-code -m anthropic/claude-sonnet-4-6 \
  --n-attempts 1 --n-concurrent 1 \
  --job-name painting-shipping-e2e-sonnet
```
