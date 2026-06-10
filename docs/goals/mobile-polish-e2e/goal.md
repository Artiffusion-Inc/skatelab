# Mobile App: Full E2E Coverage + Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement tasks task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Весь мобильный пайплайн — от записи/загрузки видео до просмотра результатов анализа — работает безупречно и покрыт E2E-тестами Maestro. Все баги по пути исправлены, UX отполирован (progress, empty, error states).

**Architecture:** KMP shared module (Ktor + auth + models) + Android Compose M3 UI. Docker Android эмулятор для E2E. Реальный бэкенд api.skatelab.ru. Video upload → WorkManager → S3/RustFS → backend session → arq worker → Vast.ai GPU → SSE progress → results display.

**Tech Stack:** Kotlin, Compose M3, Ktor 3.1.3, Hilt, Room, WorkManager, Maestro 2.6.0, Docker Android emulator

---

## Constraints

- Все Maestro-флоу должны проходить против реального бэкенда (api.skatelab.ru)
- Docker Android эмулятор — единственная платформа для E2E
- Maestro 2.6.0: `id:`, текст, `point:`, `testTag` селекторы
- Не ломать существующие тесты (shared tests, Android unit tests)
- Каждый фикс проверяется на эмуляторе: запуск → ручной проход → E2E
- Worktree mandate: все коммиты в fix-auth-testtag ветке (уже в worktree)
- r2Key → videoKey rename: убрать историческое имя поля

## Oracle

1. Все Maestro E2E флоу проходят зелёно на Docker Android эмуляторе против реального бэкенда
2. Video upload → processing → results: полный E2E flow работает на реальном устройстве
3. ProcessingScreen показывает LinearProgressIndicator с % на каждой фазе
4. Empty states на Progress, Sessions, Uploads табах
5. Error states: network, server, stuck upload, invalid video — все с retry/back

## Key Spec

`docs/specs/2026-06-10-upload-processing-ux-design.md` — полный дизайн баг-фиксов + UX полировки

## Likely Misfire

Полировать UI без проверки что backend processing pipeline реально работает. Если arq worker не запускается или SSE поток не подключается — красивый progress bar не поможет.

## Non-goals

- iOS app (только Android)
- Backend ML pipeline internals (pose estimation, tracking) — только integration points
- Performance optimization (startup time, memory) — separate goal