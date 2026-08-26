# Portable reference image for agent runners outside Harbor.
FROM ubuntu:24.04

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
