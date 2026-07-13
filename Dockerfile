# Multi-stage image for the Conference Catalog MCP server.
# Runtime must include Node/npm so npx can invoke @microsoft/events-cli.

FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

# Final runtime stage: nodejs, npm, and curl must live here (not only in builder).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && node --version \
    && npm --version \
    && npx --version \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY conferenceCatalogMCP ./conferenceCatalogMCP

USER appuser

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8010/healthz || exit 1

CMD ["uvicorn", "conferenceCatalogMCP.server:app", "--host", "0.0.0.0", "--port", "8010"]
