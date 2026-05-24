# Backend

FastAPI-based REST API for SkateLab.

## Quick Start

```bash
# Install dependencies (from repo root)
uv sync --all-packages

# Run tests
uv run pytest backend/tests/

# Run type check
uv run basedpyright backend/app/

# Run linter
uv run ruff check backend/app/

# Start development server
uv run fastapi dev backend/app/main.py
```

## Architecture

```
backend/
├── app/
│   ├── routes/          # FastAPI routers (auth, sessions, metrics, uploads, ...)
│   ├── models/          # SQLAlchemy ORM models
│   ├── crud/            # Database CRUD operations
│   ├── services/        # Business logic (diagnostics, music analysis, choreography)
│   ├── auth/            # JWT auth (deps, security)
│   ├── config.py        # Pydantic settings
│   ├── storage.py       # S3 client
│   ├── task_manager.py  # Valkey task queue helpers
│   ├── metrics_registry.py # 12+ biomechanical metric definitions
│   ├── worker.py        # arq worker (video processing, detection, music)
│   └── main.py          # FastAPI app factory
├── alembic/             # Database migrations
├── tests/               # Backend tests
└── pyproject.toml       # Backend dependencies
```

## Key Features

- **Auth**: JWT access (15min) + refresh (7d) tokens, cookie sync `sb_auth=1`
- **Rate Limiting**: slowapi — 3/min register, 5/min login (via `get_remote_address`)
- **Response Caching**: fastapi-cache2 with Redis backend — `/sessions` (60s), `/metrics/trend` (300s)
- **Storage**: S3-compatible (RustFS) via boto3, presigned URLs for direct upload
- **Async Queue**: arq + Valkey (Redis) for video processing, person detection, music analysis
- **Metrics**: 12+ biomechanical metrics with Russian labels, ideal ranges, trend analysis, diagnostics engine
- **Coach Access**: coach-student relationships via `Connection` model, permission checks via `is_connected_as`

## API Documentation

OpenAPI schema available at `/api/v1/docs` (Swagger UI) and `/api/v1/redoc` (ReDoc) when running.

## Environment Variables

See `app/config.py` for full list. Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres connection string |
| `VALKEY_HOST` / `VALKEY_PORT` | Redis/Valkey for cache + task queue |
| `S3_BUCKET` / `S3_ENDPOINT_URL` | S3-compatible storage (RustFS) |
| `JWT_SECRET_KEY` | HS256 secret for access tokens |
| `VASTAI_API_KEY` | Optional: dispatch GPU tasks to Vast.ai |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /auth/register` | 3 per minute |
| `POST /auth/login` | 5 per minute |

## Cache TTL

| Endpoint | TTL |
|----------|-----|
| `GET /sessions` | 60 seconds |
| `GET /metrics/trend` | 300 seconds |

## Testing

```bash
# All tests
uv run pytest backend/tests/

# Specific module
uv run pytest backend/tests/routes/test_sessions.py -v

# With coverage report
uv run pytest backend/tests/ --cov=backend/app --cov-report=term-missing
```

## Database Migrations

```bash
# Create migration
uv run alembic -c backend/alembic.ini revision --autogenerate -m "add new table"

# Apply migrations
uv run alembic -c backend/alembic.ini upgrade head
```

## arq Worker

Process video tasks via Valkey queue:

```bash
# Run worker
uv run arq backend/app/worker.py
```

Tasks: `process_video_task`, `detect_video_task`, `music_analysis_task`.

## Docker

```bash
# Build image (from repo root)
podman build -f backend/Containerfile -t skatelab-backend .
```

## License

MIT — see repo root `LICENSE`.
