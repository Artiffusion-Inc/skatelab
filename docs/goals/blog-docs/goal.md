# Blog & Docs (docs.skatelab.ru / blog.skatelab.ru)

## Original request
Добавить публичные docs (`docs.skatelab.ru`: user docs + закрытые dev/agent docs) и blog (`blog.skatelab.ru`) поверх существующего Next.js frontend через Fumadocs, host-based middleware, MDX в репо, i18n RU/EN path-based.

## Interpreted outcome
`docs.skatelab.ru` и `blog.skatelab.ru` отвечают, рендерят MDX-контент из `frontend/content/`. Закрытый `internal/` раздел доступен только staff (`STAFF_EMAILS`). Основной app `skatelab.ru` не сломан. Тесты зелёные.

## Input shape
`existing_plan` — план в `docs/plans/2026-07-07-blog-docs.md` (9 задач, TDD). Спека в `docs/specs/2026-07-07-blog-docs-design.md`.

## Audience / beneficiary
Пользователи продукта (user docs), команда (dev/agent docs), контент-маркетинг (blog).

## Non-goals / hard constraints
- Не Astro, не отдельный deploy-таргет — один Next.js.
- Не WYSIWYG-редактор блога (Phase 2).
- Не `User.is_staff` колонка (Phase 2; MVP = `STAFF_EMAILS` allowlist).
- Не E2E Playwright (не в scope этого goal).
- Не перенос `docs/research/` в публичный вид.
- Backend — Litestar, не FastAPI (вопреки root CLAUDE.md).
- `/internal/*` обязаны `force-dynamic`.

## Authority
`approved` — спека и план подтверждены пользователем в brainstorming.

## Proof type
`test` + `demo`.

## Completion proof
Все 9 задач плана выполнены: backend тесты (`test_users_staff_flag.py`) зелёные, frontend `bun run test && typecheck && lint` зелёные, dev-smoke через `curl -H 'Host: docs.skatelab.ru' ...` подтверждает routing+gate+content, Caddyfile валиден.

## Goal oracle
- `uv run pytest backend/tests/routes/test_users_staff_flag.py` → PASS.
- `cd frontend && bun run test && bun run typecheck` → PASS.
- `curl -H 'Host: docs.skatelab.ru' localhost:3000/ru/user/getting-started` → 200 с MDX-контентом.
- `curl -H 'Host: docs.skatelab.ru' localhost:3000/ru/internal/architecture` без cookie → redirect `/login`.
- `caddy validate` → valid configuration.

## Likely misfire
Fumadocs API версии расходится с планом → Worker правит по доке, но не обновляет plan/spec → расхождение. Защита: Worker фиксирует рабочую форму в коммите + receipt.

## Blind spots
- Fumadocs `docs.tree[loc]` / `blog.getPages(loc)` API может отличаться в установленной версии — сверить в Task 2/4/6.
- Litestar injection `AppConfig` в route — паттерн надо сверить с существующими route'ами.
- `client_factory` test-fixture имя — сверить с `test_users_routes_bugfix.py`.

## Existing plan facts
- План: `docs/plans/2026-07-07-blog-docs.md` (9 задач TDD).
- Спека: `docs/specs/2026-07-07-blog-docs-design.md`.
- Worktree: `worktree-blog-docs-design`, branch `worktree-blog-docs-design`.
- Коммиты спеки+плана: `fa7576db`, `a268f243`.
- Стек: Next.js 16 standalone, Fumadocs, next-intl, Tailwind v4, Litestar, Pydantic BaseSettings.
- Контент: MDX в `frontend/content/{docs,blog}/{ru,en}/...`.

## What counts as enough for this tranche
Все 9 задач плана выполнены и верифицированы по goal oracle. Финальный audit (Judge) подтверждает полный outcome.