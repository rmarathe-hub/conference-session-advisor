"""FastAPI entrypoint for the Conference Catalog MCP server.

JSON-RPC MCP methods and REST convenience endpoints are added in later
server wiring; health is exposed so the package is runnable early.
"""

from fastapi import FastAPI

app = FastAPI(title="conference-catalog-mcp")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
