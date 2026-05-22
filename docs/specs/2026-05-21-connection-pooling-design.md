# Phase 1a: Connection Pooling & Resource Management

**Date:** 2026-05-21
**Status:** Draft (v2 — after 5-agent deep review)
**Audited from:** Backend audit — 14 critical, ~35 high issues

## Problem

Every external connection (Valkey, R2/S3, DB) is created per-call and destroyed after use. This causes:

1. **Resource leaks** — boto3/aiobotocore clients opened per operation
2. **Shared pool kills** — `worker.py` calls `valkey.close()` in `finally`, killing the pool for all subsequent tasks
3. **Session corruption** — `DbSessionProxy._session` is a class variable, shared across requests
4. **Performance** — TLS handshake + auth per Valkey/boto3 call; offset-pagination DB queries degrade

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Valkey pool | Two pools per process (task pool `decode_responses=True` + store pool `decode_responses=False`), `get_valkey()` returns task pool | Litestar RedisStore requires `decode_responses=False`; task manager needs `decode_responses=True`; cannot merge |
| boto3/R2 sync | Per-thread client via `threading.local()`, not singleton | boto3 client is NOT thread-safe; `asyncio.to_thread` uses ThreadPoolExecutor with concurrent access under `max_jobs > 1` |
| boto3/R2 async | Lazy singleton with `asyncio.Lock` double-check + credential hash rotation | Prevents init race; auto-recreates on credential change |
| DB session | Remove `DbSessionProxy`, single `provide_db()` dependency, `except Exception` rollback | Proxy is broken (class variable sharing); narrow exception list misses DBAPIError, IntegrityError |
| DB commit | Remove auto-commit from DI; routes own commit | Current auto-commit prevents fine-grained transaction control; `@asynccontextmanager` decorator on `provide_db` is already silently broken in Litestar |
| Worker Valkey | `get_valkey()` in tasks, init in `on_startup` with retry+backoff, close in `on_shutdown` | arq provides no startup retry; Valkey unreachable = worker crash loop |
| Test isolation | `_set_test_pool()` override + `on_app_init` for DB DI | Module singletons break `unittest.mock.patch` on direct imports; Litestar DI overrides only work pre-init |

## Changes

### 1. Valkey — Two Pools Per Process (`task_manager.py`)

**Current:** `get_valkey_client()` creates new connection per call. Worker closes in `finally`. No health checks. No pool limits.

**Target:** Two `aioredis.Redis` instances per process:
- **Task pool** (`decode_responses=True`): task state, rate limiting, pub/sub PUBLISH
- **Store pool** (`decode_responses=False`): Litestar RedisStore (managed separately in lifespan)

```python
# task_manager.py — after refactor

import socket
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

_pool: aioredis.Redis | None = None
_test_pool: aioredis.Redis | None = None

def _create_redis(max_connections: int = 20) -> aioredis.Redis:
    settings = get_settings()
    url = settings.valkey.url
    common = dict(
        decode_responses=True,
        max_connections=max_connections,
        health_check_interval=30,       # PING idle connections after 30s
        socket_keepalive=True,          # TCP keepalive for stale detection
        socket_keepalive_options={
            socket.TCP_KEEPIDLE: 60,
            socket.TCP_KEEPINTVL: 10,
            socket.TCP_KEEPCNT: 3,
        },
        retry_on_timeout=True,
        retry=Retry(retries=3, backoff=ExponentialBackoff(base=1, cap=10)),
    )
    if url:
        return aioredis.Redis.from_url(url, **common)
    return aioredis.Redis(
        host=settings.valkey.host,
        port=settings.valkey.port,
        db=settings.valkey.db,
        password=settings.valkey.password.get_secret_value() or None,
        **common,
    )

async def init_valkey_pool(max_connections: int = 20) -> None:
    """Create the shared Valkey connection pool (call once at startup).

    Validates connectivity with PING. Raises on failure.
    """
    global _pool
    if _pool is not None:
        return
    client = _create_redis(max_connections=max_connections)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        raise
    _pool = client

def get_valkey() -> aioredis.Redis:
    """Return the shared Valkey connection. Raises RuntimeError if not initialised."""
    if _test_pool is not None:
        return _test_pool
    if _pool is None:
        raise RuntimeError("Call init_valkey_pool() before get_valkey()")
    return _pool

def _set_test_pool(pool: aioredis.Redis | None) -> None:
    """Test-only: override the pool singleton."""
    global _test_pool
    _test_pool = pool

async def close_valkey_pool() -> None:
    """Close the shared Valkey connection pool (call once at shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
```

All task functions drop the `valkey` optional parameter and `close` logic:

```python
async def create_task_state(task_id: str, video_key: str, user_id: str | None = None) -> None:
    valkey = get_valkey()
    # ... use valkey, no try/finally close
```

**Pub/Sub note:** `publish_task_event` uses PUBLISH (not SUBSCRIBE). PUBLISH uses a regular pool connection. SUBSCRIBE (used by SSE endpoint in `process.py`) creates a dedicated `PubSub` object with its own connection — safe. Set `max_connections` to account for concurrent SSE streams (20 + expected_streams).

**Event loop safety:** `aioredis.Redis` is bound to the event loop where it was created. `asyncio.to_thread()` does NOT change the event loop — Redis calls stay on the original loop. Document in module docstring.

### 2. Worker — Shared Valkey with Startup Retry (`worker.py`)

**Current:** `valkey = await get_valkey_client()` per task, `finally: await valkey.close()` kills pool. Startup is empty.

**Target:** Use `get_valkey()`. Init pool in arq `on_startup` with retry+backoff. Close in `on_shutdown`. Fix `async_session` import. Fix DB session rollback.

```python
# worker.py
from app.task_manager import get_valkey, init_valkey_pool, close_valkey_pool
from app.storage import close_r2_clients

async def startup(ctx: dict) -> None:
    """Initialize shared pools. Retry on Valkey failure."""
    import asyncio as _asyncio

    for attempt in range(5):
        try:
            await init_valkey_pool(max_connections=5)
            logger.info("Valkey pool initialized (attempt %d)", attempt + 1)
            break
        except (OSError, RuntimeError, ConnectionError) as e:
            wait = min(2 ** attempt, 30)
            logger.warning("Valkey pool init failed (attempt %d/5): %s, retry in %ds", attempt + 1, e, wait)
            await _asyncio.sleep(wait)
    else:
        raise RuntimeError("Failed to initialize Valkey pool after 5 attempts")

async def shutdown(ctx: dict[str, Any]) -> None:
    """Close shared pools. arq's own Redis pool is closed by Worker.close() automatically."""
    logger.info("Worker shutting down")
    await close_valkey_pool()
    await close_r2_clients()

async def process_video_task(ctx, *, task_id, ...):
    valkey = get_valkey()  # shared pool, no close
    try:
        ...
    finally:
        pass  # no valkey.close()
```

**Fix `async_session` import** (lines 248, 352): `from app.database import async_session` → `from app.database import async_session_factory`. Usage: `async with async_session_factory() as db:`.

**Add explicit rollback in worker DB sessions:**
```python
async with async_session_factory() as db:
    try:
        # ... DB operations ...
        await db.commit()
    except Exception:
        await db.rollback()
        raise
```

**Remove `shutdown` closing arq pool:** `ctx.get("redis").close()` is handled by arq's `Worker.close()`. Don't double-close.

**Write Valkey status last:** In `process_video_task`, call `store_result()` (Valkey) after DB commit to reduce DB/Valkey inconsistency:
```python
await update_progress(task_id, 0.9, "Saving results...", valkey=valkey)
# ... DB writes + commit ...
await store_result(task_id, response_data, valkey=valkey)  # LAST
```

### 3. R2/S3 — Per-Thread Sync + Async Singleton with Lock (`storage.py`)

**Current:** `_client()` creates new `boto3.client` per call. `_async_client()` creates new aiobotocore client per call + closes in `async with`. No timeouts. No credential rotation.

**Target:** Per-thread sync client (thread-safe). Async singleton with `asyncio.Lock` double-check. Explicit timeouts. Credential hash rotation. Proper cleanup.

```python
# storage.py — after refactor

import threading
import hashlib
from contextlib import suppress

_async_session = aiobotocore.session.get_session()
_thread_local = threading.local()
_async_client_instance: Any = None
_async_client_lock = asyncio.Lock()
_credential_hash: str | None = None

_R2_CONFIG = BotoConfig(
    signature_version="s3v4",
    connect_timeout=10,
    read_timeout=300,            # 5 min for large video files
    retries={"max_attempts": 3, "mode": "adaptive"},
)

def _get_credential_hash() -> str:
    s = get_settings()
    return hashlib.sha256(
        (s.r2.access_key_id.get_secret_value() + s.r2.secret_access_key.get_secret_value()).encode()
    ).hexdigest()

def get_r2_client():
    """Per-thread boto3 client (thread-safe for asyncio.to_thread)."""
    client = getattr(_thread_local, "r2_client", None)
    if client is None:
        s = get_settings()
        client = boto3.client(
            "s3",
            endpoint_url=s.r2.endpoint_url or None,
            aws_access_key_id=s.r2.access_key_id.get_secret_value(),
            aws_secret_access_key=s.r2.secret_access_key.get_secret_value(),
            config=_R2_CONFIG,
            region_name="auto",
        )
        _thread_local.r2_client = client
    return client

# Keep get_r2_client as public alias for route handlers

async def get_r2_async_client():
    """Async R2 singleton with init lock and credential rotation."""
    global _async_client_instance, _credential_hash
    current_hash = _get_credential_hash()
    if _async_client_instance is not None and _credential_hash == current_hash:
        return _async_client_instance
    async with _async_client_lock:
        # Double-check after lock
        current_hash = _get_credential_hash()
        if _async_client_instance is not None and _credential_hash == current_hash:
            return _async_client_instance
        # Close old client if credential changed
        if _async_client_instance is not None:
            with suppress(Exception):
                await _async_client_instance.__aexit__(None, None, None)
        s = get_settings()
        _async_client_instance = _async_session.create_client(
            "s3",
            endpoint_url=s.r2.endpoint_url or None,
            aws_access_key_id=s.r2.access_key_id.get_secret_value(),
            aws_secret_access_key=s.r2.secret_access_key.get_secret_value(),
            config=_R2_CONFIG,
            region_name="auto",
        )
        await _async_client_instance.__aenter__()
        _credential_hash = current_hash
    return _async_client_instance

async def reset_r2_async_client() -> None:
    """Force-recreate the async client (after unrecoverable errors)."""
    global _async_client_instance
    async with _async_client_lock:
        if _async_client_instance is not None:
            with suppress(Exception):
                await _async_client_instance.__aexit__(None, None, None)
            _async_client_instance = None

async def close_r2_clients() -> None:
    """Close all R2 clients (call at shutdown)."""
    global _async_client_instance
    if _async_client_instance is not None:
        with suppress(Exception):
            await _async_client_instance.__aexit__(None, None, None)
        _async_client_instance = None
    # Sync per-thread clients: close current thread's client
    client = getattr(_thread_local, "r2_client", None)
    if client is not None:
        client.close()
        _thread_local.r2_client = None
```

All sync functions (`upload_file`, `download_file`, etc.) use `get_r2_client()` instead of `_client()`.
All async functions (`upload_file_async`, etc.) use `await get_r2_async_client()` instead of `async with await _async_client()`. Remove `async with` wrapper from all async functions — client is long-lived.

### 4. DB Session — Remove Proxy, Fix Exception Handling (`di.py`, `database.py`)

**Current:** `DbSessionProxy` class with class variable `_session`. `@asynccontextmanager` on `provide_db` silently broken in Litestar. `except (OSError, RuntimeError, ValueError)` misses all SQLAlchemy exceptions. Auto-commit in DI prevents transaction control.

**Target:** Single `provide_db()` as plain async generator (no `@asynccontextmanager`). `except Exception` rollback. No auto-commit. Rename `db_session` param in `get_current_user`.

```python
# di.py — after refactor

async def provide_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

dependencies = {
    "settings": Provide(provide_settings),
    "db": Provide(provide_db),
    "user": Provide(get_current_user),
    "verified_user": Provide(get_verified_user),
}
```

**Remove:** `DbSessionProxy`, `db_proxy`, `db_session_proxy`, `provide_db_session`, `get_db()` from `database.py`. Remove `@asynccontextmanager` decorator.

**Rename `db_session` → `db` in `auth/deps.py`:**
```python
# auth/deps.py — change parameter name
async def get_current_user(request: Request, db: AsyncSession) -> User:
```

**Add `pool_pre_ping` and `pool_recycle` to engine** (in `database.py`):
```python
engine = create_async_engine(
    settings.database.url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,      # validate connections before use
    pool_recycle=1800,        # recycle connections after 30 min
    pool_timeout=30,
    echo=settings.app.log_level == "DEBUG",
)
```

**Test injection:** Use Litestar `on_app_init` to override dependencies before app init:
```python
# conftest.py
from litestar.config.app import AppConfig

def _make_test_app(test_session):
    async def _provide_test_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    def on_app_init(app_config: AppConfig) -> AppConfig:
        app_config.dependencies["db"] = Provide(_provide_test_db)
        return app_config

    from app.main import create_app
    # create_app must accept on_app_init parameter
    return create_app(on_app_init=on_app_init)
```

**`create_app` signature change:** Add optional `on_app_init` parameter:
```python
# main.py
def create_app(*, on_app_init: list[Callable] | None = None) -> Litestar:
    init_handlers = [jwt_auth.on_app_init]
    if on_app_init:
        init_handlers.extend(on_app_init if isinstance(on_app_init, list) else [on_app_init])
    return Litestar(
        ...
        on_app_init=init_handlers,
    )
```

### 5. Lifespan — Orchestrate All Pools with Graceful Degradation (`lifespan.py`)

```python
@asynccontextmanager
async def app_lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # 1. Valkey pool — non-fatal: app starts in degraded mode if unavailable
    try:
        await init_valkey_pool(max_connections=20)
    except (ConnectionError, OSError) as e:
        logger.warning("Valkey pool init failed — task tracking disabled: %s", e)

    # 2. R2 async client — eager init to fail fast on bad credentials
    from app.storage import get_r2_async_client, close_r2_clients
    try:
        await get_r2_async_client()
    except Exception as e:
        logger.warning("R2 client init failed: %s", e)

    # 3. Response cache store (separate pool, decode_responses=False)
    url = settings.valkey.build_url()
    redis_client = aioredis.Redis.from_url(url, decode_responses=False)
    root_store = RedisStore(redis=redis_client)
    app.stores = StoreRegistry(default_factory=root_store.with_namespace)

    # 4. arq pool
    arq_cfg = _parse_redis_url(url)
    app.state.arq_pool = await create_pool(RedisSettings(**arq_cfg))

    try:
        yield
    finally:
        # Close in reverse order; use suppress to avoid cascade failures
        with contextlib.suppress(Exception):
            await app.state.arq_pool.close()
        with contextlib.suppress(Exception):
            await close_valkey_pool()
        with contextlib.suppress(Exception):
            await close_r2_clients()
        with contextlib.suppress(Exception):
            await redis_client.aclose()
```

**Health check endpoint** reports degraded state:
```python
@get("/health")
async def health() -> dict:
    valkey_ok = False
    with contextlib.suppress(Exception):
        valkey_ok = await get_valkey().ping()
    return {"status": "ok" if valkey_ok else "degraded", "valkey": valkey_ok}
```

### 6. Worker DB Sessions (`worker.py`)

**Fix import:** `from app.database import async_session` → `from app.database import async_session_factory` at lines 248 and 352.

**Usage:** `async with async_session_factory() as db:` with explicit rollback on error.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `task_manager.py` | Remove `get_valkey_client()`, add health check + pool limits + `_set_test_pool()`, remove `valkey` params | ~180 |
| `worker.py` | `get_valkey()` instead of `get_valkey_client()`, remove `valkey.close()`, startup retry, shutdown cleanup, fix `async_session` import, add DB rollback | ~80 |
| `storage.py` | Per-thread sync client, async singleton with lock + credential hash + timeouts, proper cleanup | ~120 |
| `di.py` | Remove `DbSessionProxy`, `@asynccontextmanager`, auto-commit; add `except Exception` rollback | ~40 |
| `database.py` | Remove `get_db()`, add `pool_pre_ping`, `pool_recycle` | ~15 |
| `auth/deps.py` | Rename `db_session` → `db` parameter in `get_current_user` | ~5 |
| `main.py` | Add `on_app_init` parameter to `create_app()` | ~10 |
| `lifespan.py` | Non-fatal Valkey init, R2 eager init, graceful shutdown with `suppress` | ~25 |
| `conftest.py` (tests) | `_set_test_pool()` + `on_app_init` DI override instead of DbSessionProxy | ~30 |
| `routes/misc.py` | Add `/health` endpoint with Valkey availability check | ~10 |

## Risks

| Risk | Mitigation |
|------|------------|
| Valkey restart mid-request | `health_check_interval=30` + `retry_on_timeout=True` + `Retry(retries=3)` auto-reconnects stale connections |
| R2 endpoint goes down | botocore built-in retry (5 attempts adaptive mode); `reset_r2_async_client()` for manual recovery |
| Credential rotation | Hash comparison on each `get_r2_async_client()` call auto-recreates client |
| Worker startup Valkey failure | Retry with exponential backoff (5 attempts, max 30s wait) |
| App can't reach Valkey at startup | Non-fatal: app starts in degraded mode, `/health` reports `degraded`, task-related endpoints return 503 |
| Pub/sub connections exhausting pool | `max_connections=20` sized for concurrent SSE streams; `PubSub` gets dedicated connection |
| Test isolation | `_set_test_pool()` for Valkey; `on_app_init` for DB DI override; both avoid `unittest.mock.patch` on direct imports |
| Two Valkey pools in same process | Documented: task pool (decode_responses=True) + store pool (decode_responses=False); cannot merge |

## Out of Scope

- Offset → keyset pagination — Phase 2a
- Metric direction bug — Phase 2a
- Auth/security hardening — Phase 1b
- Error handling (worker task stuck RUNNING, suppress→log) — Phase 2b
