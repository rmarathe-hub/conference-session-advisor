# Testing (Phase 0–2 MCP server)

Default suite (no live catalog / network CLI):

```bash
python3.12 -m pip install -r requirements.txt
python3.12 -m pytest
python3.12 -m pytest -q
python3.12 -m pytest --cov=conferenceCatalogMCP --cov-report=term-missing
```

Explicitly exclude optional live CLI tests (also the default via `pytest.ini`):

```bash
python3.12 -m pytest -m "not real_cli"
```

Optional live `@microsoft/events-cli` checks:

```bash
python3.12 -m pytest -m real_cli
```
