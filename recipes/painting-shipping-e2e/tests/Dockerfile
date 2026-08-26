FROM ubuntu:24.04

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Pre-install the claude CLI at a pinned version so the rewardkit agent judge
# never runs its unpinned latest-version installer at verification time, and
# allow the read-only tools the headless judge needs to inspect the workspace.
RUN curl -fsSL https://claude.ai/install.sh | bash -s 2.1.243 \
    && mkdir -p /root/.claude \
    && printf '%s\n' '{"permissions": {"allow": ["Read", "Grep", "Glob"]}}' \
        > /root/.claude/settings.json
ENV PATH="/root/.local/bin:${PATH}"

COPY . /tests
RUN chmod +x /tests/test.sh

WORKDIR /tests
