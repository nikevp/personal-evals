FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

WORKDIR /app
COPY runtime.py server.py sidecar.py logistics.py sidecar-response.schema.json ./
RUN mkdir -p /state && uv sync --script server.py

EXPOSE 8000
CMD ["uv", "run", "server.py"]
