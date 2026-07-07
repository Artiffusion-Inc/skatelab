---
title: "Blog & Docs (docs.skatelab.ru / blog.skatelab.ru)"
date: "2026-07-07"
status: draft
---

# Blog & Docs — Fumadocs на существующем Next.js

**Date:** 2026-07-07
**Status:** Draft
**Scope:** Два публичных subdomain (`docs.skatelab.ru`, `blog.skatelab.ru`) поверх одного Next.js frontend через host-based middleware + Fumadocs. User docs (открытые) + blog компании + закрытые dev/agent docs (role-gate). i18n RU/EN, path-based локаль для docs/blog. Контент — MDX в репо, публикация через PR.

---

## Контекст и ограничения

- Frontend — один Next.js 16 app (`frontend/src/app`), standalone-билд, обслуживается Caddy-блоком `skatelab.ru` → `frontend:3000`.
- i18n сейчас **cookie-based** (`NEXT_LOCALE`, `frontend/src/i18n/request.ts`, allow-list `ru`/`en`). Подходит для продукта (authed user), но ломает SEO контент-сайта: локаль не в URL, нет канонических ссылок, hreflang нерабочий.
- Auth: JWT (`backend/app/auth/deps.py`), cookie `sk_session`. `User` не имеет глобального `is_staff`/`is_admin` — есть только `onboarding_role` (строка онбординга) и `WorkspaceRole` (роль внутри workspace, не глобальная).
- Caddy (`infra/caddy/Caddyfile`) уже роутит `api.skatelab.ru` и `skatelab.ru`; поддомены вроде `rss.{$DOMAIN}` добавляются одним блоком.

## Решения

### 1. Routing & subdomain

Один Next.js, host-based middleware.

**Caddy** (`infra/caddy/Caddyfile`) — два новых блока, зеркало `skatelab.ru` (TLS dns cloudflare, тот же header-сет security):

```
docs.skatelab.ru {
  tls { dns cloudflare {env.CLOUDFLARE_API_TOKEN} { propagation_timeout -1 } }
  header { /* те же HSTS/X-Frame/... что у skatelab.ru */ }
  handle { reverse_proxy frontend:3000 { /* тот же health/flush/timeout */ } }
}
blog.skatelab.ru { /* аналогично */ }
```

Cloudflare DNS — две записи (A/CNAME) на тот же origin, что `skatelab.ru`.

**Middleware** (`frontend/src/middleware.ts`, расширяет существующий postHog-middleware):
- Читает `request.headers.host`.
- `docs.skatelab.ru` → rewrite на route-группу `/docs` (`frontend/src/app/(docs)/...`).
- `blog.skatelab.ru` → rewrite на `/(blog)/...`.
- `skatelab.ru` / `www.skatelab.ru` → текущее поведение без изменений.
- Matcher: `/((?!_next/static|_next/image|favicon.ico|api).*)` (как сейчас).
- postHog-middleware продолжает работать поверх.

**Route structure:**

```
frontend/src/app/
  (docs)/
    [locale]/                  # /ru, /en  (path-based)
      layout.tsx               # DocsLayout: sidebar, nav, search, chrome
      user/[[...slug]]/page.tsx     # открытые user docs
      internal/[[...slug]]/page.tsx # закрытые dev/agent docs (role-gate, force-dynamic)
      sitemap.ts               # docs.skatelab.ru/sitemap.xml (user only; internal не в sitemap)
      robots.ts                # disallow /internal/
  (blog)/
    [locale]/
      layout.tsx               # blog layout
      page.tsx                 # список постов
      [slug]/page.tsx          # пост
      sitemap.ts
      rss.ts                   # опционально, RSS feed (Phase 2)
```

Locale в URL только для docs/blog. Основной app остаётся cookie-based — два режима разделены по host, не конфликтуют.

### 2. Контент & MDX pipeline

MDX-файлы в репо, git-tracked, публикуются через PR.

**Структура:**

```
frontend/content/
  docs/
    ru/
      user/                    # открытые: загрузка видео, отчёты, профиль, API product
        getting-started.mdx
        upload-video.mdx
        ...
      internal/                # закрытые: architecture, ml-pipeline, roadmap
        architecture.mdx
        ml-pipeline.mdx
        roadmap.mdx
        ...
    en/
      user/...
      internal/...
  blog/
    ru/
      2026-07-07-launch.mdx    # frontmatter: title, date, author, excerpt, tags, coverAlt
      ...
    en/
      ...
```

**Frontmatter:**
- blog: `title`, `date` (ISO), `author`, `excerpt`, `tags`, `coverAlt` (опц. `cover`).
- docs: `title`, `description`, `icon` (опц.).

**Fumadocs MDX** (`@fumadocs/mdx`):
- `source.config.ts` описывает `docs` и `blog` sources, карты локалей.
- Loader компилирует MDX в билдтайме, search-индекс (Orama, без Algolia-зависимости) генерится автоматически.
- Картинки — static imports или `/public/content/*`, asset-path через Fumadocs.

**i18n-сопоставление:** один и тот же slug в `ru/` и `en/`. Ссылка на `/en/<slug>` если файл существует, иначе fallback на `ru` + banner «перевод отсутствует» (namespace `docs.translation-missing` / `blog.translation-missing` в messages). Chrome-строки (nav, search placeholder, footer) — переиспользуют next-intl messages с новыми namespace `docs.*`, `blog.*` в `messages/ru.json` / `en.json`.

**Sitemap/SEO:**
- `app/(docs)/[locale]/sitemap.ts` (один на subdomain через `app/(docs)/sitemap.ts` если host-detect позволяет; иначе статические пути) → `docs.skatelab.ru/sitemap.xml` только user-страницы. `internal/` исключён из sitemap.
- `hreflang` link-tags на RU/EN варианты того же slug.
- `robots.txt`/`robots.ts`: user docs/blog allow, `/internal/` disallow (двойная защита: robots + role-gate).

### 3. Auth-gate для dev docs

Закрытый раздел `internal/` под основным auth (JWT), role-gate. Не отдельный механизм.

**Признак сотрудника (MVP, ponytail):**
- Env `STAFF_EMAILS` в `backend/app/config.py` (server-side, НЕ `NEXT_PUBLIC`). Список email'ов основателей (`mi@...`, `alisa@...`).
- Ноль миграций, ноль колонок.
- Upgrade path: когда появится админка → колонка `User.is_staff` + Alembic миграция, allowlist удалить. Отметить TODO в спеке и в config-коде.

**Backend:**
- Существующий `/v1/users/me` дополняется полем `isStaff: bool` — сервер сверяет email пользователя с `STAFF_EMAILS`. Один чек на бэке, env не дублируется на frontend.
- Новой endpoint-модели не требуется; расширение response-схемы `UserMe` (или эквивалент) одним полем.

**Frontend gate** — page-level, не middleware (middleware занят host-роутингом):
- `app/(docs)/[locale]/internal/[[...slug]]/page.tsx` (server component):
  - Читает JWT-cookie через `cookies()`, вызывает существующий API-клиент `/v1/users/me`.
  - Нет токена / `isStaff === false` → `redirect('/login?next=<url>')`.
  - `isStaff === true` → рендер MDX.
- **`export const dynamic = 'force-dynamic'` на `/internal/*`** — обязательный. Иначе Fumadocs может отдать MDX как static/built артефакт, и контент утечёт без auth. Gate выполняется per-request. Это ключевой security-пункт спека.

### 4. Брэндинг & общий layout

Один продукт, два subdomain — общий визуальный язык.

**Переиспользуется:**
- Tailwind config, design tokens (`frontend/src/app/tokens.css`), shadcn-компоненты.
- Fumadocs `DocsLayout` / `DocsBody` обёрнуты в существующий root-стиль; Fumadocs theme приравнен к нашему `primary` из `tokens.css`.
- next-intl messages (общие файлы, новые namespace).
- Theme-provider (`frontend/src/app/providers.tsx`) — dark/light/system уже есть.
- Locale switcher — path-based: на `/ru/upload-video` линк на `/en/upload-video` если существует. Переиспользовать существующий компонент если есть, иначе минимальный.

**Отличается от основного app:**
- Header/footer docs/blog — упрощённые: лого + locale-switcher + (docs) search-bar. Без app-навигации (dashboard/upload/etc), без auth-menu кроме link «войти».
- Логотип/брэнд — тот же что на landing, ссылка на `skatelab.ru`.

**Cross-link:**
- docs → продукт: link «Open app» на `skatelab.ru/dashboard` (если authed) или `/login`.
- blog → docs: в постах MDX линковка на docs-страницы через Fumadocs `<Link>`.
- основной app → docs: footer/help-link на `docs.skatelab.ru`.

**Fumadocs UI** тащит свой набор компонентов + стилей; интегрируется через `tailwindcss-plugin` в существующий `tailwind.config` и один `@import` в `globals.css`. Ноль отдельного CSS-фреймворка.

### 5. Тесты & verify

MVP-проверки, не full-suite.

**Backend (pytest):**
- Unit: `is_staff` true/false для email в/вне `STAFF_EMAILS` (env-mock). Один тест.
- Integration: authed `/v1/users/me` → `isStaff: false` по умолчанию, `true` когда email в allowlist.

**Frontend (vitest):**
- Middleware host-routing: `docs.skatelab.ru` → rewrite `/docs`, `blog.skatelab.ru` → `/blog`, `skatelab.ru` → unchanged. postHog-middleware не сломан.
- Locale-param: path-based `[locale]` валидируется (ru/en), fallback ru.
- Internal gate: unauthenticated → redirect `/login`; authed non-staff → redirect/403; authed staff → 200. Mock `/v1/users/me`.
- `force-dynamic` на `/internal/*`: assert, что static-export не рендерит internal без gate (через явную проверку или build-artifact inspect).

E2E Playwright **не добавляется** (YAGNI для этого спека; был гэп vs Open SaaS, но не входит в scope).

Каждый шаг плана сопровождается failing-test-first → fix (по CLAUDE.md принципу verifiable goals).

## За рамками (Phase 2 / future)

- WYSIWYG-редактор блога для не-кодеров (когда Алиса упрётся с PR).
- `User.is_staff` колонка + миграция (замена `STAFF_EMAILS` allowlist).
- RSS feed для blog.
- E2E Playwright suite (отдельная задача).
- Перенос `docs/research/` (R&D-заметки) в публичный вид — отдельный decision, не в этом спеке.

## Open questions / TODO

- Проверить, какой именно response-тип возвращает текущий `/v1/users/me` (имя схемы/поля), чтобы корректно добавить `isStaff`. — Выясняется на этапе реализации.
- Подтвердить, что Caddy `reverse_proxy` health_uri `/` годится для docs/blog root (или нужен fallback-route).