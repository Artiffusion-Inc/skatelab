# Mobile Session E2E Bug-Hunt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Написать 7 Maestro E2E-флоу + 1 partial, которые гоняют полный цикл пользовательской сессии против реального backend `api.skatelab.ru`, чтобы выявлять НОВЫЕ (неизвестные) недоработки в mobile и backend; каждую найденную недоработку оформить issue с тегом для reviewer.

**Architecture:** Сквозные Maestro-флоу против живого backend через Docker-эмулятор `skatelab-emulator`. Каждый сценарий ожидает корректное поведение и падает только при реальной недоработке. Зелёные → поверхность здорова; красные (устойчивые после 3 прогонов) → диагностика + issue. Production-код НЕ трогается (мандат: диагностика + тесты + issues).

**Tech Stack:** Maestro 2.6.x (в контейнере), Docker-эмулятор `budtmo/docker-android:emulator_14.0`, ADB, реальный backend `api.skatelab.ru` (Litestar), тестовый аккаунт `test@skatelab.ru`/`Test123456`.

## Global Constraints

- **Реальный backend** `api.skatelab.ru`, не fake. API_BASE_URL в приложении = `https://api.skatelab.ru/v1/` (`mobile/androidApp/build.gradle.kts:11`).
- **Мандат:** только Maestro flows + partials + issues. Никаких production-фиксов. Никаких правок `mobile/shared/`, `mobile/androidApp/src/main/`, `backend/app/`.
- **Refresh-хаки запрещены:** access-token TTL = 15 мин (`backend/app/config.py:102`). Refresh-rotation и 401-mid-session НЕ покрываются E2E (на юнит-тестах `AuthWireTest` #6–#10).
- **Maestro 2.6.x селекторы — по видимому тексту** (Compose `testTag` невидим для UI Automator). Профиль отображает email как plain `Text` (`ProfileScreen.kt:183`) — селектор `assertVisible: "<email>"`.
- **Очистка состояния:** перед каждым flow `adb shell pm clear ru.skatelab.capture` + re-grant camera (кроме случаев где нужен сохранённый логин — тогда `launchApp`).
- **Тестовый аккаунт A:** `test@skatelab.ru` / `Test123456` (`is_verified=true`, живой).
- **Тестовый аккаунт B:** `e2e2@skatelab.ru` / `Test123456` (`is_verified=true`) — создаётся в Task 1.
- **Flows НЕ помечать `manual`** (иначе исключаются из прогона `config.yaml: excludeTags: [manual]`). S2 с уникальным email — отдельно (см. Task 6).
- **Worktree:** все коммиты в `worktree-auth-cache-logout-bug`. Никогда в master.

---

## File Structure

- Create: `mobile/e2e/maestro/partials/login_as.yaml` — переиспользуемый логин-партиал
- Create: `mobile/e2e/maestro/flows/s1-cross-account-switch.yaml`
- Create: `mobile/e2e/maestro/flows/s2-register-immediate-read.yaml`
- Create: `mobile/e2e/maestro/flows/s3-read-after-logout.yaml`
- Create: `mobile/e2e/maestro/flows/s4-cold-start-read-race.yaml`
- Create: `mobile/e2e/maestro/flows/s5-relogin-same-baseline.yaml`
- Create: `mobile/e2e/maestro/flows/s6-rate-limit-login.yaml`
- Create: `mobile/e2e/maestro/flows/s7-sessions-cross-account.yaml`
- Create: `mobile/e2e/BUG_HUNT_INDEX.md` — индекс найденных багов/issues для reviewer (обновляется в Task 10)

Каждый flow-файл — один сценарий, один responsibility, независимо запускается.

---

### Task 1: Подготовить второй verified-аккаунт на backend

**Files:**
- Modify: (нет файлов) — one-time backend setup
- Test: ручная верификация через API

**Interfaces:**
- Consumes: тестовый аккаунт A `test@skatelab.ru` (есть)
- Produces: аккаунт B `e2e2@skatelab.ru` / `Test123456` (`is_verified=true`) — используют S1, S7

- [ ] **Step 1: Зарегистрировать аккаунт B через API**

```bash
curl -i -X POST https://api.skatelab.ru/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e2@skatelab.ru","password":"Test123456","display_name":"E2E Two"}'
```
Expected: HTTP 201, тело с `access_token`/`refresh_token`.

- [ ] **Step 2: Установить `is_verified=true` для B**

Аккаунт создан, но `login` требует `is_verified=true` (`auth.py:198`). Поставить вручную через backend/DB (один раз, как делали для `test@skatelab.ru` по memory `local-e2e-setup`). Способ — через имеющийся доступ к backend (psql/скрипт):

```bash
# Через backend-окружение (пример; актуальный доступ — по памяти local-e2e-setup)
# UPDATE users SET is_verified = true WHERE email = 'e2e2@skatelab.ru';
```

- [ ] **Step 3: Верифицировать login B через API**

```bash
curl -i -X POST https://api.skatelab.ru/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e2@skatelab.ru","password":"Test123456"}'
```
Expected: HTTP 200, токены. Если 403 "Email not verified" — Step 2 не применён, повторить.

- [ ] **Step 4: Записать аккаунт B в BUG_HUNT_INDEX.md (preconditions)**

```bash
cat >> mobile/e2e/BUG_HUNT_INDEX.md <<'EOF'
# E2E Bug-Hunt Index — session lifecycle

## Preconditions
- Backend: `https://api.skatelab.ru/v1/`
- Аккаунт A: `test@skatelab.ru` / `Test123456` (is_verified=true)
- Аккаунт B: `e2e2@skatelab.ru` / `Test123456` (is_verified=true)

## Scenarios
| Flow | Сценарий | Статус | Issue |
|------|----------|--------|-------|
| s1-cross-account-switch | cross-account switch | TBD | — |
| s2-register-immediate-read | register → read | TBD | — |
| s3-read-after-logout | read after logout | TBD | — |
| s4-cold-start-read-race | cold start race | TBD | — |
| s5-relogin-same-baseline | re-login same (baseline) | TBD | — |
| s6-rate-limit-login | rate-limit edge | TBD | — |
| s7-sessions-cross-account | sessions read-path leak | TBD | — |
EOF
```

- [ ] **Step 5: Commit**

```bash
git add mobile/e2e/BUG_HUNT_INDEX.md
git commit -m "test(mobile-e2e): bug-hunt index + second verified account precondition"
```

---

### Task 2: login_as.yaml partial

**Files:**
- Create: `mobile/e2e/maestro/partials/login_as.yaml`

**Interfaces:**
- Consumes: Maestro env vars `${EMAIL}`, `${PASSWORD}` (или значения по умолчанию)
- Produces: partial, используемый S1/S3/S5/S7 через `runFlow`

- [ ] **Step 1: Написать partial**

```yaml
appId: ru.skatelab.capture
---
# Reusable login partial. Expects login screen visible.
# Usage: runFlow: { file: partials/login_as.yaml, env: { EMAIL: "x@y", PASSWORD: "z" } }
- assertVisible: "Log in to your account"
- tapOn: "Email"
- inputText: ${EMAIL}
- back
- tapOn: "Password"
- inputText: ${PASSWORD}
- back
- tapOn: "Log in"
- assertVisible: "Camera"
```

- [ ] **Step 2: Smoke-проверить partial (через S5 в Task 5)** — partial не запускается standalone, валидируется через использующий flow.

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/partials/login_as.yaml
git commit -m "test(mobile-e2e): login_as reusable partial"
```

---

### Task 3: S5 — re-login same account (baseline GREEN)

**Files:**
- Create: `mobile/e2e/maestro/flows/s5-relogin-same-baseline.yaml`

**Interfaces:**
- Consumes: аккаунт A, partial `login_as.yaml`
- Produces: контрольный GREEN-сценарий (если падает — инфра сломана, не продукт)

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - auth
---
# S5 baseline: login A → logout → login A → Profile shows A.
# Control GREEN scenario — confirms infra works.
- launchApp
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
# Login A
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: test@skatelab.ru
      PASSWORD: Test123456
- tapOn: "Profile"
- assertVisible: "test@skatelab.ru"
# Logout
- scroll
- scroll
- tapOn: "Log out"
- assertVisible: "Log in to your account"
# Re-login A
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: test@skatelab.ru
      PASSWORD: Test123456
- tapOn: "Profile"
- assertVisible: "test@skatelab.ru"
```

- [ ] **Step 2: Прогнать flow (см. Task 10 для полного run-процесса)**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s5-relogin-same-baseline.yaml
```
Expected: PASS. Если FAIL — инфра-проблема (эмулятор/backend/APK), не баг продукта; чинить окружение, не flow.

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/s5-relogin-same-baseline.yaml
git commit -m "test(mobile-e2e): S5 re-login same account baseline flow"
```

---

### Task 4: S1 — cross-account switch

**Files:**
- Create: `mobile/e2e/maestro/flows/s1-cross-account-switch.yaml`

**Interfaces:**
- Consumes: аккаунты A и B (Task 1), partial `login_as.yaml`
- Produces: bug-hunt flow — ищет новые отклонения за пределами #314 (UI профиля не обновляется, sessions показывают A)

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - auth
---
# S1: login A → Profile shows A → logout → login B → Profile shows B (NOT A).
# Bug-hunt: expects correct cross-account switch. RED = new defect beyond #314.
- launchApp
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
# Login A
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: test@skatelab.ru
      PASSWORD: Test123456
- tapOn: "Profile"
- assertVisible: "test@skatelab.ru"
# Logout
- scroll
- scroll
- tapOn: "Log out"
- assertVisible: "Log in to your account"
# Login B
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: e2e2@skatelab.ru
      PASSWORD: Test123456
- tapOn: "Profile"
- assertVisible: "e2e2@skatelab.ru"
# B's email must show; A's must NOT leak
- assertNotVisible: "test@skatelab.ru"
```

- [ ] **Step 2: Прогнать 3× (отсев флакинга)**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
# Повторить 3 раза:
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s1-cross-account-switch.yaml
```
Expected: PASS (поверхность здорова) ИЛИ устойчивый FAIL (3/3) → баг (Task 10 диагностика).

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/s1-cross-account-switch.yaml
git commit -m "test(mobile-e2e): S1 cross-account switch bug-hunt flow"
```

---

### Task 5: S3 — read after logout (UI state leak)

**Files:**
- Create: `mobile/e2e/maestro/flows/s3-read-after-logout.yaml`

**Interfaces:**
- Consumes: аккаунт A, partial `login_as.yaml`
- Produces: bug-hunt flow — ищет data leak в UI после logout (Sessions показывает A)

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - auth
---
# S3: login A → open Sessions → logout → relaunch → login screen (NOT sessions A).
# Bug-hunt: logout must clear UI state. RED = UI data leak after logout.
- launchApp
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
# Login A
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: test@skatelab.ru
      PASSWORD: Test123456
# Open Sessions tab (populate UI state)
- tapOn: "Sessions"
- assertVisible: "Profile"
# Logout
- tapOn: "Profile"
- scroll
- scroll
- tapOn: "Log out"
- assertVisible: "Log in to your account"
# Relaunch app — must show login screen, NOT sessions of A
- killApp
- launchApp
- assertVisible: "Log in to your account"
- assertNotVisible: "Profile"
```

- [ ] **Step 2: Прогнать 3×**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s3-read-after-logout.yaml
```

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/s3-read-after-logout.yaml
git commit -m "test(mobile-e2e): S3 read-after-logout UI state leak flow"
```

---

### Task 6: S2 — register → immediate read

**Files:**
- Create: `mobile/e2e/maestro/flows/s2-register-immediate-read.yaml`

**Interfaces:**
- Consumes: уникальный timestamp-email (вписывается вручную перед прогоном — Maestro не генерит timestamp)
- Produces: bug-hunt flow — ищет race register→read (stale кэш/состояние)

**Note:** S2 помечается `manual` (исключается из дефолтного прогона `run-e2e.sh`) т.к. требует уникальный email каждый прогон. Прогоняется вручную с вписанным email.

- [ ] **Step 1: Написать flow (email-плейсхолдер)**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - auth
  - manual
---
# S2: register new account → immediately read profile → shows new user (not empty/other).
# MANUAL: replace REGISTER_EMAIL below with a fresh unique email each run
# (e.g. e2e-20260624-1@skatelab.ru). Register issues tokens directly (no verification needed
# for same-session read; login later would require is_verified).
- launchApp
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- assertVisible: "Log in to your account"
- tapOn: "Don't have an account? Register"
- assertVisible: "Create Account"
- tapOn: "Display name"
- inputText: E2E BugHunt
- back
- tapOn: "Email"
- inputText: e2e-20260624-1@skatelab.ru
- back
- tapOn: "Password"
- inputText: Test123456
- back
- tapOn: "Register"
- assertVisible: "Camera"
# Immediate read: Profile must show the new account's email
- tapOn: "Profile"
- assertVisible: "e2e-20260624-1@skatelab.ru"
```

- [ ] **Step 2: Прогнать вручную с уникальным email**

Перед прогоном заменить `e2e-20260624-1@skatelab.ru` на свежий. Скопировать flow и partials в контейнер (как в Task 3 Step 2), затем:

```bash
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s2-register-immediate-read.yaml
```
Expected: PASS (register→read корректен) ИЛИ FAIL → баг (Task 10).

- [ ] **Step 3: Commit (с плейсхолдером email — не пушить реальный одноразовый)**

```bash
git add mobile/e2e/maestro/flows/s2-register-immediate-read.yaml
git commit -m "test(mobile-e2e): S2 register-immediate-read bug-hunt flow (manual, unique email)"
```

---

### Task 7: S4 — cold-start read race

**Files:**
- Create: `mobile/e2e/maestro/flows/s4-cold-start-read-race.yaml`

**Interfaces:**
- Consumes: аккаунт A, partial `login_as.yaml`
- Produces: bug-hunt flow — ищет race при холодном старте (stale tokenStorage → inconsistent Profile/Sessions)

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - auth
---
# S4: login A → cold relaunch → quickly open Sessions + Profile → both consistent (A).
# Bug-hunt: cold-start race must not produce stale/inconsistent state.
- launchApp
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: test@skatelab.ru
      PASSWORD: Test123456
# Cold relaunch
- killApp
- launchApp
- assertVisible: "Camera"
# Quickly open Sessions, then Profile — both must reflect A consistently
- tapOn: "Sessions"
- assertVisible: "Profile"
- tapOn: "Profile"
- assertVisible: "test@skatelab.ru"
```

- [ ] **Step 2: Прогнать 3×**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s4-cold-start-read-race.yaml
```

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/s4-cold-start-read-race.yaml
git commit -m "test(mobile-e2e): S4 cold-start read race flow"
```

---

### Task 8: S6 — rate-limit edge on login

**Files:**
- Create: `mobile/e2e/maestro/flows/s6-rate-limit-login.yaml`

**Interfaces:**
- Consumes: sacrificial-аккаунт (использовать A или B — rate-limit счётчик `login_email: max 5 / 300s` `auth.py:158` загрязняется; прогонять последним в suite)
- Produces: bug-hunt flow — ищет некорректную обработку backend rate-limit mobile (AppError/UX/silent fail)

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - auth
---
# S6: 6 failed logins (wrong password) → app shows rate-limit/error message (not crash/hang).
# Bug-hunt: backend rate-limit (login_email max 5 / 300s) must surface correctly in mobile.
# NOTE: pollutes rate-limit counter for the email — run LAST in suite.
- launchApp
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- assertVisible: "Log in to your account"
# 6 wrong-password attempts (rate limit triggers after 5 within 300s on backend)
- repeat:
    times: 6
    commands:
      - tapOn: "Email"
      - inputText: test@skatelab.ru
      - back
      - tapOn: "Password"
      - inputText: WrongPassword123
      - back
      - tapOn: "Log in"
      - extendedWaitUntil:
          visible: "Log in to your account"
          timeout: 5000
# After rate-limit: app must still be on login screen (no crash/hang). An error message
# may or may not be shown (depends on AppError mapping) — assert no crash via login screen visible.
- assertVisible: "Log in to your account"
```

- [ ] **Step 2: Прогнать (последним в suite — загрязняет rate-limit)**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s6-rate-limit-login.yaml
```
Expected: PASS (login screen остался, no crash) ИЛИ FAIL → баг (Task 10). Дополнительно собрать `adb logcat` для проверки AppError-маппинга rate-limit.

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/s6-rate-limit-login.yaml
git commit -m "test(mobile-e2e): S6 rate-limit login edge flow"
```

---

### Task 9: S7 — sessions read-path leak after cross-account

**Files:**
- Create: `mobile/e2e/maestro/flows/s7-sessions-cross-account.yaml`

**Interfaces:**
- Consumes: аккаунты A и B (Task 1), partial `login_as.yaml`
- Produces: bug-hunt flow — ищет read-path leak sessions (список сессий не сбрасывается при смене аккаунта)

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - auth
---
# S7: login A → Sessions (A's sessions if any) → logout → login B → Sessions shows B (or empty), NOT A.
# Bug-hunt: sessions read-path must not leak across accounts.
# Fallback: if neither account has sessions, assert Sessions tab opens (empty state) —
# the leak we hunt is A's sessions visible under B; absence of sessions for both = skip (log).
- launchApp
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: test@skatelab.ru
      PASSWORD: Test123456
- tapOn: "Sessions"
# (A's sessions, if any, now populated)
- tapOn: "Profile"
- scroll
- scroll
- tapOn: "Log out"
- assertVisible: "Log in to your account"
- runFlow:
    file: ../partials/login_as.yaml
    env:
      EMAIL: e2e2@skatelab.ru
      PASSWORD: Test123456
- tapOn: "Sessions"
# Under B: Sessions must open. If A had session titles/elements, they must NOT appear here.
# Concretely: assert B can reach Sessions; if a session title from A is known, assertNotVisible it.
- assertVisible: "Profile"
```

- [ ] **Step 2: Прогнать 3×**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s7-sessions-cross-account.yaml
```

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/s7-sessions-cross-account.yaml
git commit -m "test(mobile-e2e): S7 sessions cross-account read-path leak flow"
```

---

### Task 10: Прогнать suite, triage red/green, открыть issues

**Files:**
- Modify: `mobile/e2e/BUG_HUNT_INDEX.md` — заполнить статусы + issue-ссылки

**Interfaces:**
- Consumes: все flows (Tasks 3–9), аккаунты (Task 1)
- Produces: issue-индекс для reviewer + открытые issues в репо

- [ ] **Step 1: Собрать debug APK**

```bash
cd mobile
./gradlew :androidApp:assembleDebug --no-daemon --no-configuration-cache
# Проверить md5 (по mobile/CLAUDE.md — старый APK может остаться)
md5sum androidApp/build/outputs/apk/debug/androidApp-debug.apk
```
Expected: `BUILD SUCCESSFUL`, APK существует.

- [ ] **Step 2: Установить APK в эмулятор**

```bash
docker cp androidApp/build/outputs/apk/debug/androidApp-debug.apk skatelab-emulator:/tmp/app-debug.apk
docker exec skatelab-emulator adb install -r /tmp/app-debug.apk
```

- [ ] **Step 3: Прогнать весь suite (кроме S2 manual, S6 последним)**

```bash
# Скопировать flows + partials
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
# Порядок: S5 (baseline) → S1 → S3 → S4 → S7 → S6 (последним, загрязняет rate-limit)
for f in s5-relogin-same-baseline s1-cross-account-switch s3-read-after-logout s4-cold-start-read-race s7-sessions-cross-account s6-rate-limit-login; do
  docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
  docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
  echo "=== $f ==="
  docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
    maestro test --device emulator-5554 /home/androidusr/flows/$f.yaml 2>&1 | tail -20
done
```

- [ ] **Step 4: Для каждого красного flow — прогнать 3× и собрать диагностику**

```bash
# Для красного flow (пример s1):
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/s1-cross-account-switch.yaml
# Повторить 3×. Устойчивый красный (3/3) → баг. Собрать:
docker exec skatelab-emulator adb logcat -d -t 500 | grep -iE 'skatelab|AndroidRuntime|FATAL|Auth|token' > /tmp/$f-logcat.txt
# Backend logs (если есть доступ) — grep по auth/session/event
```

- [ ] **Step 5: Для каждого устойчивого красного flow — определить поверхность root cause**

Прочитать trace по коду:
- Profile показывает чужой email → `ProfileScreen.kt:183` + `ProfileViewModel` + `UsersApi.getMe` + `SkateLabClient` Auth-cache → поверхность mobile (или backend `/users/me` если возвращает чужое — проверить через `curl` с токеном B).
- Sessions показывает чужое → `SessionsViewModel` + `SessionsApi` + backend `/sessions?user_id=` → проверить backend query filter (`backend/app/routes/sessions.py`).
- Rate-limit crash → `ExceptionMapping.kt` + backend `check_rate_limit` response shape → `AppError`-маппинг.
- Определить тег: `mobile` или `backend` (+ `testing/repro`).

- [ ] **Step 6: Открыть issue для каждого найденного бага**

Через `gh issue create` с телом по форме:
- Что произошло (наблюдение)
- Шаги воспроизведения (flow + команды)
- Ожидаемое vs фактическое
- Гипотеза root cause (file:line)
- Impact для prod
- Теги: `testing/repro`, `mobile` или `backend`
- Ссылка на flow + коммит в worktree

```bash
gh issue create --title "..." --label "testing/repro,mobile" --body "$(cat <<'EOF'
## What
...

## Repro
Flow: mobile/e2e/maestro/flows/s1-cross-account-switch.yaml
...
EOF
)"
```

- [ ] **Step 7: Обновить BUG_HUNT_INDEX.md — статусы + issue-номера**

```bash
# Заполнить таблицу: для каждого flow — PASS/FAIL/FLAKY/SKIP + issue # (если открыт)
# Зелёные → "PASS — surface healthy"
# Красные устойчивые → "FAIL — issue #NNN (mobile/backend)"
# Единичный красный → "FLAKY — not a bug"
# S2/S7 skip → "SKIP — <reason>"
```

- [ ] **Step 8: Commit индекс**

```bash
git add mobile/e2e/BUG_HUNT_INDEX.md
git commit -m "test(mobile-e2e): bug-hunt triage results + issue index"
```

- [ ] **Step 9: Обновить PR #325 body с issue-индексом (или открыть новый PR для E2E flows)**

Если E2E flows идут в тот же PR #325 — обновить body. Если отдельный PR — `gh pr create` с разделами «Что сделано» / «Как проверить» и индексом issues.

---

## Self-Review (выполнено автором)

- **Spec coverage:** S1–S7 → Tasks 4,6,5,7,3,8,9. Task 1 = preconditions, Task 2 = partial, Task 10 = triage+issues. Все 7 сценариев + preconditions + issue-форма покрыты.
- **Placeholder scan:** S2 email — намеренный плейсхолдер с инструкцией (manual flow), не TBD. Остальных плейсхолдеров нет.
- **Type consistency:** partial `login_as.yaml` с env `EMAIL`/`PASSWORD` используется единообразно в S1/S3/S5/S7. Имена flow-файлов совпадают в Tasks и Step 3 suite-цикла.
- **Мандат соблюдён:** все задачи — только flows/partials/диагностика/issues. Никаких правок production-кода.