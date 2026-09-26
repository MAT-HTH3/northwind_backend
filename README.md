# northwind-backend

Back-end for the Northwind support chat widget ([northwind-frontend](../northwind-frontend)):
a FastAPI service with a LangGraph agent on Gemini that decides whether a customer's request
can be resolved by the AI Assistant or must be handed to a Human Agent.

- Domain vocabulary: [`CONTEXT.md`](CONTEXT.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- API the widget expects: [`northwind-frontend/docs/api-contract.md`](../northwind-frontend/docs/api-contract.md)

## Run it

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 for you).

```bash
cp .env.example .env          # then set GEMINI_API_KEY
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload
```

The API is on http://localhost:8000 (interactive docs at `/docs`). Point the widget at it by
setting `NEXT_PUBLIC_USE_MOCK_API=false` in the front-end's `.env.local`.

## Develop

```bash
uv run pytest                              # fast; Gemini is faked
RUN_LIVE_LLM=1 uv run pytest -k live       # real Gemini calls to check the prompts
uv run ruff check . && uv run ruff format .
uv run alembic revision --autogenerate -m "describe the change"
```

## Layout

```
src/
  main.py          FastAPI app, CORS, routers
  core/config.py   Settings, loaded from .env
  core/db.py       async SQLAlchemy engine, session, declarative Base
  models/          tables this service owns (Support Cases, readings, resolutions)
  repositories/    data access used by the graph and routes; methods flush, callers commit
  legacy/          mock Legacy Systems (Legacy Billing, Metering, CRM, CaseTrack) + fixtures
  schemas/         request/response models shared with the widget contract
  history/         Unified Customer History: merges the Legacy Systems and our Support Cases
  agent/           LangGraph support graph: state, nodes, checkpointer, turn helpers
  api/routes/      HTTP endpoints
alembic/           database migrations
```

The database is SQLite for now. The schema is kept Postgres-compatible, so moving to
Postgres (Tiger Data) means changing `DATABASE_URL` to a `postgresql+asyncpg://` URL.
