# E2E Bug-Hunt: жизненный цикл сессии против реального backend

**Дата:** 2026-06-24
**Статус:** Approved
**Worktree:** `worktree-auth-cache-logout-bug`
**Мандат:** диагностика + тесты + issues. Никаких production-фиксов в этой работе.
**Связано:** продолжение `2026-06-23-mobile-auth-session-test-suite-design.md` (юнит/repro-тесты auth/session). Этот спека — сквозной E2E-охват той же поверхности против реального backend.

## Назначение

Набор Maestro E2E-флоу, которые гоняют **полные циклы пользовательской сессии против реального backend** `api.skatelab.ru`, чтобы **выявлять новые (неизвестные) недоработки** в mobile и в backend. Это НЕ воспроизведение уже найденного бага #314, а стресс соседних сценариев той же поверхности.

**Принцип поиска новых багов, не воспроизведения известных:** каждый сценарий построен как «ожидаем корректное поведение» и падает, **только если** встречает реальную недоработку. Зелёный сценарий подтверждает здоровье поверхности; красный — находит новый баг.

## Форма результата каждой найденной недоработки

Issue в репо с тегом:
- `testing/repro` — если недоработка воспроизводится сквозным E2E (по convention `2026-06-23`).
- `mobile` — если root cause в mobile (UI не обновляется, кэш/состояние stale, AppError-маппинг).
- `backend` — если root cause в backend (sessions-API возвращает чужое, rate-limit-семантика, refresh).

Содержание issue (для быстрого разбора reviewer):
- Что произошло (наблюдаемое поведение).
- Шаги воспроизведения (Maestro flow + команды).
- Ожидаемое vs фактическое.
- Гипотеза root cause с trace по коду (file:line).
- Impact для prod (data leak / UX / silent fail).
- Ссылка на Maestro flow + коммит в worktree.

**Фиксы — отдельные PR по этим issue.** Эта работа не трогает production-код.

## Принципы ограничений (verbatim из решений)

- Подход A — цикл сессии (auth + read-path). Upload/processing (B) и панель зондов (C) — следующие итерации.
- E2E без refresh-хаков: refresh-rotation (access-token TTL = 15 минут, `backend/app/config.py:102`) и 401-mid-session остаются на юнит-тестах `AuthWireTest` #6–#10. E2E стрессует только поверхности с реалистичным таймингом.
- Реальный backend, не fake. Тестовый аккаунт `test@skatelab.ru` / `Test123456` живой на `api.skatelab.ru` (`is_verified=true`).

## Сценарии

Каждый сценарий — отдельный Maestro flow в `mobile/e2e/maestro/flows/`. Селекторы по видимому тексту (ограничение Maestro 2.6.x — Compose `testTag` невидим для UI Automator).

### S1. Cross-account switch (`s1-cross-account-switch.yaml`)
login A (`test@skatelab.ru`) → logout → login B (второй аккаунт) → открыть Profile → ассертить, что показан B (displayName/email), не A.
**Ищет:** новые отклонения за пределами #314 — UI профиля не обновляется даже при корректном токене, или sessions-вкладка показывает сессии A после login B.
**Preconditions:** второй verified-аккаунт на backend.

### S2. Register → immediate read (`s2-register-immediate-read.yaml`)
register нового аккаунта (детерминированный timestamp-email) → сразу открыть Sessions/Profile → ассертить, что профиль нового пользователя (не пустой, не чужой).
**Ищет:** race между register и первым read — кэш/состояние stale после register.

### S3. Read sessions after logout, без повторного login (`s3-read-after-logout.yaml`)
login A → открыть Sessions → logout → снова launchApp → ассертить login screen (не sessions A).
**Ищет:** logout не очищает UI-состояние sessions/profile — после logout вкладка Sessions показывает данные A (data leak в UI).

### S4. Concurrent launch + read (race при холодном старте) (`s4-cold-start-read-race.yaml`)
login A → launchApp повторно (cold start) → быстро открыть Sessions и Profile → ассертить консистентность (оба показывают A).
**Ищет:** race при холодном старте — ViewModel инициализируется из stale tokenStorage до инвалидации.

### S5. Re-login same account — baseline (`s5-relogin-same-baseline.yaml`)
login A → logout → login A → Profile показывает A.
**Назначение:** контрольный GREEN-сценарий. Подтверждает, что базовый цикл здоров; если падает — инфра сломана, а не продукт.

### S6. Rate-limit edge на login (`s6-rate-limit-login.yaml`)
login A с неверным паролем 5+ раз подряд → ассертить, что появляется rate-limit/сообщение об ошибке (не краш, не зависание).
**Ищет:** backend rate-limit (`login_email: max 5 / 300s`, `backend/app/routes/auth.py`) не обрабатывается корректно mobile — AppError-маппинг, UI-сообщение, или silent fail.

### S7. Sessions tab после cross-account — read-path leak (`s7-sessions-cross-account.yaml`)
login A → дождаться появления сессий A (если есть) → logout → login B → открыть Sessions → ассертить, что показаны сессии B (или пусто), **не** сессии A.
**Ищет:** read-path leak sessions — список сессий кэшируется/не сбрасывается при смене аккаунта.

## Test doubles и preconditions

- **Второй verified-аккаунт** на `api.skatelab.ru`. Сейчас есть только `test@skatelab.ru`. Нужен второй (`e2e2@skatelab.ru` / `Test123456`, `is_verified=true`) для S1/S7. Создаётся через backend один раз, вне flow. В flows — константы.
- **Precondition-партиал:** `mobile/e2e/maestro/partials/login_as.yaml` — переиспользуемый логин с параметрами (email/password через env/Maestro config).
- **Сессии для S7:** если у test-аккаунтов нет сессий, S7 деградирует к «пустой список → ассертить пустоту, не чужое». Если ни у кого нет сессий — сценарий skip с пометкой в issue-индексе (не silent cap — логируем, что пропущено и почему).
- **Очистка состояния:** перед каждым flow — `adb shell pm clear ru.skatelab.capture` + re-grant camera (по convention `local-e2e-setup`). Запуск с login screen.

## Поток выполнения и верификация

1. Создать второй verified-аккаунт на backend (один раз, вручную через API/DB).
2. Написать 7 Maestro flows в `mobile/e2e/maestro/flows/` + 1 partial (`partials/login_as.yaml`).
3. Прогнать локально через `mobile/e2e/run-e2e.sh --apk-path <apk>` (или поштучно `maestro test --device emulator-5554 <flow>`).
4. Для каждого **красного** flow:
   - Прогнать 3× (отсеять Maestro-флакинг).
   - Устойчивый красный → диагностика: `adb logcat` + backend logs + trace по коду (file:line).
   - Определить поверхность root cause (mobile/backend).
   - Открыть issue с тегом (`testing/repro` + `mobile`/`backend`) по форме выше.
   - Единичный красный → флакинг, не issue (логируем отдельно).
5. Для каждого **зелёного** flow — записать в индекс «поверхность здорова».
6. Issue-индекс в PR-описании: список всех открытых issues с тегами и кратким описанием для reviewer.
7. **Никаких production-фиксов.** PR содержит только flows + partials. Красные flows остаются красными как доказательство.

## Scope

- 7 Maestro flows + 1 partial.
- Второй test-аккаунт на backend (один раз).
- Прогон против реального backend.
- Issues на найденные баги (mobile/backend), PR с flow-файлами.

## Non-goals

- Production-фиксы (отдельные PR по issues).
- Refresh-rotation / 401-mid-session E2E (на юнит-тестах `AuthWireTest` #6–#10).
- Upload/processing surfaces (подход B — следующая итерация).
- Панель зондов по нескольким поверхностям (подход C — следующая итерация).
- CI-интеграция E2E (локальный прогон; CI — отдельная работа).
- Frontend-тесты (отдельная поверхность).
- Воспроизведение #314 как цели (юнит-тесты уже покрывают; E2E ищет новое).

## Риски

- **E2E-флакинг Maestro 2.6.x** (dADB-таймауты) → красный не значит баг. Каждый красный flow прогоняется 3×; устойчивый красный → баг, единичный → флакинг (не issue).
- **Реальный backend mutability** — S2 (register) создаёт аккаунты на prod-backend. Детерминированные timestamp-based email, пометка «одноразовые». Уникальные email избегают накопления.
- **S6 rate-limit загрязняет backend-счётчик** для test-аккаунта → прогонять последним, или на отдельном sacrificial-аккаунте.
- **Сессии для S7** могут отсутствовать → сценарий skip с пометкой (не silent cap, логируем).
- **Второй аккаунт** — если нельзя создать на prod, S1/S7 блокируются → фолбэк на единственный аккаунт с пометкой охвата в issue-индексе.

## Связанные артефакты

- `docs/specs/2026-06-23-mobile-auth-session-test-suite-design.md` — юнит/repro-тесты auth/session (PR #325).
- `docs/plans/2026-06-23-mobile-auth-session-test-suite.md` — план юнит-тестов.
- `mobile/e2e/maestro/flows/` — существующие 15 Maestro flows (login, register, logout, и др.).
- `mobile/CLAUDE.md` — E2E-инфра, Maestro-грабли, тестовый аккаунт.
- Memory `local-e2e-setup` — Docker-эмулятор + Maestro, реальный backend E2E рабочий.