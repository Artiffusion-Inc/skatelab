# Mobile App: Full E2E Coverage + Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement tasks task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Покрыть всё Android-приложение SkateLab E2E-тестами Maestro, отполировать UX, исправить все краши и баги, найти при ручном проходе — не останавливаемся пока всё не работает как часы.

**Architecture:** KMP shared module (Ktor + auth + models) + Android Compose M3 UI. Docker Android эмулятор для E2E. Реальный бэкенд api.skatelab.ru.

**Tech Stack:** Kotlin, Compose M3, Ktor 3.1.3, Hilt, Maestro 2.6.0, Docker Android emulator

---

## Constraints

- Все Maestro-флоу должны проходить против реального бэкенда (api.skatelab.ru)
- Docker Android эмулятор — единственная платформа для E2E
- Maestro 2.6.0: только `id:`, текст, и `point:` селекторы (нет testTag, нет contentDescription)
- Не ломать существующие тесты (shared tests, Android unit tests)
- Каждый фикс проверяется на эмуляторе: запуск → ручной проход → E2E
- Worktree mandate: все коммиты в fix-auth-testtag ветке (уже в worktree)

## Oracle

Полный набор Maestro E2E флоу проходит зелёно на Docker Android эмуляторе против реального бэкенда. Приложение не крашится ни на одном экране. Каждый пользовательский поток (auth → dashboard → session list → session detail → upload → profile) покрыт E2E-тестом.