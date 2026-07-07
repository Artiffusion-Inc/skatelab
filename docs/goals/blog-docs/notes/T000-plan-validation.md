# T000 — Judge: Validate plan vs spec

**Decision:** revised — план approve с правками Task 1 (backend config/route/test паттерны).

## Findings

### F1 — Config access pattern (WRONG in plan)
Plan Task 1 Step 5 инжектит `AppConfig` в `get_me` как DI-параметр. Реальность:
- `AppConfig` в `app/main.py` — это Litestar `litestar.config.app.AppConfig` (init-хук), НЕ наш settings.
- Route'ы достают settings через `get_settings()` функцию (`from app.config import get_settings`), см. `routes/auth.py:27,78`, `auth/deps.py:12,50`.
- `Settings` (root) содержит вложенные `*Config`. `StaffConfig` надо добавить в `Settings`, не в `AppConfig`.

**Fix:** `StaffConfig` → поле `staff` в `Settings` (как `resend`, `posthog`). `get_me` → `get_settings().staff.emails`.

### F2 — `STAFF_EMAILS` env → list[str] parsing
Pydantic v2 `BaseSettings` парсит comma-string в `list[str]` **только** с `env_parse_none_str`/CSV если настроено. `CORSConfig.origins` имеет default list, не env-driven пример. `worker_retry_delays: list[int]` — default list. Нет примера env-driven list в коде.

**Fix:** добавить `@field_validator("emails", mode="before")` сплитит строку по `,` (handle both list и string). Безопасно.

### F3 — Test fixture reality (CRITICAL)
`backend/tests/conftest.py` `client` fixture:
- `skip_auth=True` → `CurrentUser` = first active user в db (НЕ JWT flow). Но тесты `test_users_routes_bugfix.py` создают real user + real JWT + `Authorization: Bearer` header → `skip_auth=True` всё равно, но header передаётся. Сверить: при `skip_auth` `get_current_user` игнорирует JWT и берёт first active user. Значит email-fixed test невозможен через `skip_auth`.
- fixture **мокает `app.main.get_settings`** (MagicMock), НЕ `app.config.get_settings`. Route'ы импортируют `from app.config import get_settings` → в тесте получают **real cached Settings** (env-based).
- `Settings` — `@lru_cache` singleton → `monkeypatch.setenv("STAFF_EMAILS")` НЕ подействует после первого импорта (кеш).

**Fix:** test патчит `app.config.get_settings` (или `app.routes.users.get_settings`) через `monkeypatch.setattr` возвращать Settings с нужным `staff.emails`. ИЛИ `get_settings.cache_clear()` + setenv перед каждым тестом. Чище — `monkeypatch.setattr("app.routes.users.get_settings", lambda: FakeSettings(staff=StaffConfig(emails=[...])))`.

Для auth flow: `skip_auth=True` берёт first active user — нельзя тестить «staff vs non-staff by email» через client fixture напрямую. Альтернатива: unit-test `is_staff` логики изолированно (вынести `compute_is_staff(email, settings) -> bool` чистую функцию) + integration test что `/me` возвращает `is_staff` поле (без проверки конкретного email, через patch get_settings). **Рекомендую: вынести чистую функцию `is_staff_email(email, staff_emails) -> bool`** — unit-test тривиален, integration test проверяет только наличие поля + что get_me её зовёт (patch get_settings).

### F4 — Fumadocs API version
Не проверял установленную версию (нет в репо ещё — Task 2 устанавливает). План корректно говорит «сверить в Step 6/7». Оставить как есть, Worker фиксирует рабочую форму.

### F5 — `force-dynamic` leak risk
План верно отмечает. Оставить.

## Plan corrections applied
- Task 1 Step 3: `StaffConfig` → `Settings` field, не `AppConfig`.
- Task 1 Step 5: `get_me` → `get_settings().staff.emails` через `get_settings()`.
- Task 1 Step 1: tests — вынести `is_staff_email()` чистую функцию + unit-test; integration test через patch `get_settings`.
- Task 1 Step 3: `@field_validator` для comma-split.

## Verdict
full_outcome_complete: false. План валиден структурно, правки Task 1 внесены. Worker T001 может стартовать с исправленным Task 1. Остальные tasks (T002–T009) без структурных правок — Fumadocs API сверки оставлены на Worker'а.