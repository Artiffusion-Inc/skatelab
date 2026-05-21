# Phase 1a: Connection Pooling & Resource Management

**Date:** 2026-05-21
**Status:** Draft
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
| Valkey pool | Single pool per process, `get_valkey()` returns shared instance | Worker and app are separate processes; each gets its own pool at startup |
| boto3/R2 | Lazy singleton sync + async clients, initialized in lifespan | aiobotocore manages HTTP connection pool internally; we just need one client |
| DB session | Remove `DbSessionProxy`, single `provide_db()` dependency | Litestar already provides per-request scoping via `Provide`; proxy adds unnecessary complexity |
| Worker Valkey | Pass `get_valkey()` instance to task functions, never close in `finally` | Pool lifecycle managed by arq `on_startup`/`on_shutdown` |

## Changes

### 1. Valkey — Unified Pool (`task_manager.py`)

**Current:** `get_valkey_client()` creates new connection per call. All task functions use it. Worker calls `valkey.close()` in `finally`.

**Target:** Single `aioredis.Redis` instance per process. Init in lifespan (app) or `on_startup` (worker). No per-call creation or close.

```python
# task_manager.py — after refactor

_pool: aioredis.Redis | None = None

async def init_valkey_pool() -> None:
    global _pool
    if _pool is not None:
        return
    _pool = _create_redis()

def get_valkey() -> aioredis.Redis:
    if _pool is None:
        raise RuntimeError("Call init_valkey_pool() before get_valkey()")
    return _pool

async def close_valkey_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
```

All task functions (`create_task_state`, `update_progress`, etc.) drop the `valkey` optional parameter and `close` logic:

```python
async def create_task_state(task_id: str, video_key: str, user_id: str | None = None) -> None:
    valkey = get_valkey()
    # ... use valkey, no try/finally close
```

**Migration:** All callers that pass `valkey=` keyword drop it. All `finally: await valkey.close()` blocks removed.

### 2. Worker — Shared Valkey (`worker.py`)

**Current:** `valkey = await get_valkey_client()` per task, `finally: await valkey.close()` kills pool.

**Target:** Use `get_valkey()`. Init pool in arq `on_startup`, close in `on_shutdown`.

```python
# worker.py
from app.task_manager import get_valkey, init_valkey_pool, close_valkey_pool

async def startup(ctx: dict) -> None:
    await init_valkey_pool()

async def shutdown(ctx: dict) -> None:
    await close_valkey_pool()

async def process_video_task(ctx, *, task_id, ...):
    valkey = get_valkey()  # shared pool, no close
    try:
        ...
    finally:
        pass  # no valkey.close()
```

### 3. R2/S3 — Singleton Clients (`storage.py`)

**Current:** `_client()` creates new `boto3.client` per call. `_async_client()` creates new `aiobotocore` client per call + closes in `async with`.

**Target:** Lazy singleton clients, initialized once.

```python
# storage.py — after refactor

_sync_client: boto3.client | None = None
_async_client_instance: aiobotocore.S3Client | None = None

def get_r2_client():
    global _sync_client
    if _sync_client is None:
        s = get_settings()
        _sync_client = boto3.client(
            "s3",
            endpoint_url=s.r2.endpoint_url or None,
            aws_access_key_id=s.r2.access_key_id.get_secret_value(),
            aws_secret_access_key=s.r2.secret_access_key.get_secret_value(),
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )
    return _sync_client

async def get_r2_async_client():
    global _async_client_instance
    if _async_client_instance is None:
        s = get_settings()
        _async_client_instance = _async_session.create_client(
            "s3",
            endpoint_url=s.r2.endpoint_url or None,
            aws_access_key_id=s.r2.access_key_id.get_secret_value(),
            aws_secret_access_key=s.r2.secret_access_key.get_secret_value(),
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )
        await _async_client_instance.__aenter__()
    return _async_client_instance

async def close_r2_clients() -> None:
    global _sync_client, _async_client_instance
    if _async_client_instance is not None:
        await _async_client_instance.__aexit__(None, None, None)
        _async_client_instance = None
    _sync_client = None
```

All sync functions (`upload_file`, `download_file`, etc.) use `get_r2_client()` instead of `_client()`.
All async functions (`upload_file_async`, etc.) use `get_r2_async_client()` instead of `async with await _async_client()`.

**Cleanup:** `close_r2_clients()` called in lifespan shutdown.

### 4. DB Session — Remove Proxy (`di.py`, `database.py`)

**Current:** `DbSessionProxy` class with class variable `_session`. Two instances `db_proxy` and `db_session_proxy`. Also `get_db()` in `database.py` and `provide_db()` in `di.py` — three session providers.

**Target:** Single `provide_db()` function. Test injection via Litestar `on_app_init` override.

```python
# di.py — after refactor

async def provide_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except (OSError, RuntimeError, ValueError):
            await session.rollback()
            raise

dependencies = {
    "settings": Provide(provide_settings),
    "db": Provide(provide_db),
    "user": Provide(get_current_user),
    "verified_user": Provide(get_verified_user),
}
```

**Remove:** `DbSessionProxy`, `db_proxy`, `db_session_proxy`, `provide_db_session`, `get_db()` from `database.py`.

**Test injection:** In `conftest.py`, override the `db` dependency:

```python
# conftest.py
app = create_app()
app.dependencies["db"] = Provide(lambda: test_session)
```

### 5. Lifespan — Orchestrate All Pools (`lifespan.py`)

```python
@asynccontextmanager
async def app_lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # 1. Valkey pool (shared by task_manager + worker)
    await init_valkey_pool()

    # 2. R2 async client (lazy, but init eagerly for health check)
    from app.storage import get_r2_async_client, close_r2_clients
    await get_r2_async_client()

    # 3. Response cache store
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
        await app.state.arq_pool.close()
        await close_valkey_pool()
        await close_r2_clients()
        await redis_client.aclose()
```

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `task_manager.py` | Remove `get_valkey_client()`, remove `valkey` params, remove `close` logic | ~180 |
| `worker.py` | Replace `get_valkey_client()` → `get_valkey()`, remove `valkey.close()`, add startup/shutdown | ~50 |
| `storage.py` | Singleton clients, remove `_client()`, remove `async with await _async_client()` | ~100 |
| `di.py` | Remove `DbSessionProxy`, `db_proxy`, `db_session_proxy`, `provide_db_session`; keep `provide_db` | ~30 |
| `database.py` | Remove `get_db()` | ~10 |
| `lifespan.py` | Add R2 client init/cleanup, close redis_client | ~15 |
| `conftest.py` (tests) | Override `db` dependency instead of DbSessionProxy injection | ~10 |

## Risks

| Risk | Mitigation |
|------|------------|
| Stale R2 client after credential rotation | Singleton re-creates on `None`; add manual `close_r2_clients()` if needed |
| Worker process doesn't call lifespan | Worker uses arq `on_startup`/`on_shutdown` to call `init_valkey_pool`/`close_valkey_pool` |
| Test isolation with shared pool | Tests mock `get_valkey()` and `get_r2_async_client()` at module level |

### 6. Worker DB Sessions (`worker.py`)

Worker creates DB sessions directly via `async_session_factory()` (line 248, 785). This is correct — worker runs outside Litestar DI. No change needed, but document that `async_session` import path (`from app.database import async_session`) may be a typo — should be `async_session_factory`. Verify and fix if needed.

## Out of Scope

- DB connection pool tuning (pool_size, max_overflow) — separate concern
- Offset → keyset pagination — Phase 2a
- Metric direction bug — Phase 2a
- Auth/security hardening — Phase 1b
