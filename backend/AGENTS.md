# Backend

Litestar 2 API under `/v1`; async SQLAlchemy/PostgreSQL; Valkey/arq queues; S3-compatible storage.

## Entry Points

- `app/main.py` — Litestar factory, JWT, middleware, route registration.
- `app/routes/` — HTTP controllers.
- `app/models/`, `app/crud/` — persistence layer.
- `app/services/` — business logic.
- `app/worker.py` — fast/heavy arq workers and Vast.ai dispatch.
- `alembic/` — schema migrations.

## Rules

- Routes do not import ML pipeline internals. Worker may use stable `src` types/helpers but never run heavy inference locally.
- Auth uses access/refresh JWT in httpOnly cookies. Preserve ownership checks for user, coach, and workspace data.
- Keep transactions explicit: commit complete state, rollback failures, never report completion before durable writes.
- Add Alembic migration for schema changes; never mutate production schema manually.
- Litestar errors and response schemas must match frontend/mobile contracts.

## Verify

```bash
uv run pytest backend/tests/ -v --tb=short --import-mode=importlib
uv run ruff check backend/
uv run basedpyright --level error backend/app
cd backend && uv run alembic upgrade head
```
