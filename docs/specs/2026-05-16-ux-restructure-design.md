# UX Restructure Design

**Date:** 2026-05-17 (rev 2 — second-round review incorporated)
**Scope:** Full frontend (Next.js 16 app)
**Current Score:** 19/40 (Poor — Nielsen heuristics), 0/40 (WCAG 2.1 AA)
**Target Score:** 30+/40 (Good — Nielsen), 24+/40 (WCAG AA)

---

## 1. Current State Audit

### 1.1 Heuristic Evaluation (19/40)

| # | Heuristic | Score | Problem |
|---|-----------|-------|---------|
| H1 | Visibility of System Status | 2/4 | No loading skeletons on 6 pages, no error states on 8 pages, processing replaces whole page |
| H2 | Match System / Real World | 2/4 | Nav labels already in Russian via `ru.json`, but metric names in session cards use snake_case, route paths are English |
| H3 | User Control and Freedom | 1/4 | No undo for delete, email verify = dead end (forces re-login after verify), Compare orphan page |
| H4 | Consistency and Standards | 2/4 | Same action (delete) works differently per page, empty states inconsistent, nav changes conditionally |
| H5 | Error Prevention | 1/4 | Delete next to share as peer, no confirmation for bulk delete, Compare page has zero guard |
| H6 | Recognition over Recall | 1/4 | Users must remember session IDs for compare, metric names in snake_case |
| H7 | Flexibility and Efficiency | 2/4 | No keyboard shortcuts, no recent items, power users see same UI as beginners |
| H8 | Aesthetic and Minimalist Design | 2/4 | Session detail: 4-5 visible actions equal weight, Progress: 14-16 decisions on load, dashboard: bare "Loading..." |
| H9 | Error Recovery | 1/4 | 8/10 data pages have no error state, "not found" has no CTA, API errors silently swallowed |
| H10 | Help and Documentation | 1/4 | No contextual help, no tooltips, tour shows before user has context |

### 1.2 Priority Issues

| Priority | Issue | Impact | Fix |
|----------|-------|--------|-----|
| P0 | 8/10 data pages missing error states | Users see blank on API failure | `usePageStatus` hook + `<ErrorState>` component + explicit conditional rendering |
| P0 | 6/10 pages missing loading states | Blank screen while fetching | Add skeleton loaders |
| P0 | Email verification blocks signup | Forces re-login after verify | Inline verify modal, keep user in context |
| P0 | No demo session for new users | 4-10 min to aha, most abandon | Pre-load sample analysis |
| P1 | Session detail: flat layout, 4-5 actions equal weight | No visual hierarchy, destructive next to benign | Tab-based progressive disclosure |
| P1 | Progress: 14-16 simultaneous decisions | Cognitive overload | 3-level progressive disclosure |
| P1 | Compare page: no empty/error/loading | Dead end if <2 sessions | Full state coverage |
| P1 | Metric names in snake_case | Users see `max_height` not "Высота прыжка" | Localize via `registry?.label_ru` |
| P2 | Processing replaces whole page | User loses all context | Sticky progress banner |
| P2 | Connections empty state href="#" | Dead end on primary CTA | Inline invite form |
| P2 | No global error toast | API failures silently swallowed | QueryCache.onError handler |
| P2 | Filter-empty vs data-empty not distinguished | "No sessions" when filter returns zero | Add "No matching sessions" state |
| P0 | App scores 0/40 on WCAG 2.1 AA | Nested `role="button"` conflicts, PhaseTimeline not keyboard operable, 3D viewer mouse-only, color-only indicators | See Section 9 |
| P0 | `detect.py` and `process.py` have NO AUTH | Anyone can enqueue GPU jobs and upload to R2 | Add `CurrentUser` dependency to both routes |
| P1 | Missing rate limits on uploads, presign, sessions | GPU/R2 cost abuse vector | Add rate limiting middleware |

---

## 2. Target Information Architecture

### 2.1 Mental Model: ELEMENT-MASTERY

Skaters think in **elements** (axel, lutz, salchow) → **sessions** (recordings of attempts) → **improvement** (progress over time). The product mirrors this cycle:

```
SKATE → RECORD → ANALYZE → IMPROVE
  ↑                              |
  └──────────────────────────────┘
```

### 2.2 Navigation Structure

**Universal primary nav** (4 items + center FAB, bottom dock on mobile):

| Position | Icon | Label (ru) | Label (en) | Route |
|----------|------|------------|------------|-------|
| 1 | `Newspaper` | Записи | Sessions | `/feed` |
| 2 | `BarChart3` | Прогресс | Progress | `/progress` |
| 3 | `Music` | Программа | Programs | `/choreography` |
| 4 | `User` | Профиль | Profile | `/profile` |
| Center FAB | `Camera` | + Загрузка | + Upload | `/upload` |

**Why universal nav instead of role-adaptive:**
- Role-adaptive excludes multi-role users (coach who also skates)
- Creates chicken-and-egg: nav needs role, but role selected after first analysis
- Flash risk: nav renders before `fetchMe()` resolves
- Universal nav with role-based **page sections** is simpler and more robust

**Center FAB caveat:** 4/10 confidence for utility apps (per competitive research). Social apps use center FAB for creation; SkateLab is a utility app where "upload" is the primary action but not the ONLY action. If center FAB causes accessibility or safe-area issues, fall back to a persistent "Загрузить видео" banner at the top of `/feed` (content-area FAB). The nav slot becomes a 4th item instead.

**Coach-specific features — view switcher, not tabs:**
- Progress and Dashboard pages use a **view switcher** (like ClassDojo's student/teacher toggle) instead of tabs
- Switcher: "Мой прогресс ↔ Ученики" on Progress, "Мои сессии ↔ Ученики" on Dashboard
- This follows dual-role UX norms: tabs imply separate sections, switcher implies same-place different lens
- Switcher state persists per user (localStorage `coach_view_mode`)

**Key renames (revised based on audit):**

| Current | Proposed (ru) | Rationale |
|---------|---------------|-----------|
| Feed (Лента) | Записи | Accurately describes session cards, not social media |
| Upload (Загрузка) | Загрузка (keep) | Users need to know this is where they upload. "Разбор" describes result, not action |
| Progress (Прогресс) | Прогресс (keep) | Shows trends over time. "Результаты" conflicts with session detail scores |
| Planner (Планировщик) | Программа | Correct figure skating domain term for choreography programs |
| Dashboard (Ученики) | Ученики (keep) | Correct for coaches, conditional in nav |

**Contextual (not in primary nav):**

| Feature | Placement | When visible |
|---------|-----------|-------------|
| Compare | Standalone `/compare` route + action from session detail Export tab | Direct link or session detail |
| Connections | Profile submenu | When user needs to invite/link |
| Settings | Profile submenu | Always (under avatar) |
| Dashboard | Conditional nav item for coaches | When `onboarding_role === "coach"` OR `hasStudents` |

### 2.3 Page Hierarchy

| Page | Route | P0 Content | P1 Content | P2 Content | Primary CTA |
|------|-------|------------|------------|------------|-------------|
| Записи | `/feed` | Session cards grid | Filters, search | Bulk actions | "Загрузить видео" |
| Загрузка | `/upload` | DropZone + progress | Camera option | ZIP with IMU | Select file |
| Прогресс | `/progress` | Element cards (L0) | Element detail (L1) | Metric deep dive (L2) | Tap element card |
| Программа | `/choreography` | Program list | New program flow | Music analysis | "Новая программа" |
| Ученики (coach) | `/dashboard` | Student list with alerts | Student detail | Diagnostics overview | "Пригласить" |
| Сессия | `/sessions/[id]` | Score + Video + Recommendations | Frame chart + 3D + Full metrics | Downloads + Compare + Delete | Play video |
| Профиль | `/profile` | Stats summary | Sessions list | Settings link | View sessions |
| Сравнение | `/compare` | Session pickers + side-by-side | Metric diff table | Skeleton overlay diff | Select sessions |

---

## 3. Key Page Redesigns

### 3.1 Session Detail: Tab-Based Progressive Disclosure

**Current:** Flat 2-column layout, 4-5 visible actions, 3D always loaded via `React.lazy`.

**Proposed:** 3 tabs — Overview (default), Details, Export.

#### Tab 1: Overview (Обзор)

```
+-------------------------------------------------------+
| [Element Name]          [Score: 7.2/10]       [... v] |  ← Score in header, menu collapses actions
| 12 мая 2026                                           |
+-------------------------------------------------------+
| [VideoWithSkeleton — full width, hero]                 |
+-------------------------------------------------------+
| [PhaseTimeline — thin strip, video scrubber]           |
+-------------------------------------------------------+
| Рекомендации                                           |
| - Слегка согните колено при приземлении               |
| - Удерживайте корпус вертикально                       |
+-------------------------------------------------------+
| Метрики (only out-of-range + PRs)                      |
| [Показать все метрики →]  links to Details tab        |
+-------------------------------------------------------+
```

**`[...v]` menu:** Share, Compare, Print, Delete (destructive at bottom, red).

#### Tab 2: Details (Детали)

```
+-------------------------------------------------------+
| [FrameMetricsChart — full width]                       |
| [PhaseTimeline — synced with chart]                    |
+-------------------------------------------------------+
| [ThreeJSkeletonViewer]     | Full Metrics Table       |  ← 3D loaded ONLY on tab switch
| Camera: Front/Side/Top     | All 12+ metrics          |
+-------------------------------------------------------+
| Диагностика (was wrongly titled "Рекомендации")        |
+-------------------------------------------------------+
```

#### Tab 3: Export (Экспорт)

```
+-------------------------------------------------------+
| Скачать                                                |
| [Видео]  [Скелет]  [Биомеханика CSV]                  |
| Сравнить                                               |
| [Выбрать сессию →]  → /compare?left={currentId}      |
| Действия                                               |
| [Поделиться]  [Печать отчёта]                          |
| [Удалить сессию] ← isolated, red, bottom               |
+-------------------------------------------------------+
```

**Note on Export tab vs overflow menu:** Competitive analysis shows no sports app has Export as a tab. The Export tab is retained for this spec because it consolidates all secondary actions (share, compare, delete, download) into one progressive-disclosure location, reducing visual clutter on Overview and Details tabs. If user testing shows low tab engagement, move Export actions to an `[...v]` overflow menu on Overview and remove the third tab entirely.

**Processing state:** Sticky banner with progress bar instead of full-page replacement. Failed state keeps video playable (original `video_url`).

**Tab state management:** Use URL search param `?tab=overview|details|export` for shareability and back-button support. Default to `overview`.

**Key improvements:**
- Score promoted to header (large, color-coded)
- Recommendations above metrics (actionable > numeric)
- 3D viewer gated behind Details tab (saves GPU — already `React.lazy`, now also conditionally mounted)
- Compare starts from Export tab with session picker, pre-fills `left` param
- `/compare` remains standalone for deep-linking and arbitrary comparison
- Delete isolated and visually separated
- Actions collapsed to 1 visible (menu) + tab disclosure

### 3.2 Progress Page: 3-Level Progressive Disclosure

**Current:** 8 element buttons + 9-metric dropdown + period selector = 14-16 simultaneous decisions.

**Proposed:** 3 levels, one decision at a time.

#### Level 0: Element Overview (`/progress`)

Grid of element cards, each showing:
- Element name (localized)
- Health indicator: Green (improving/PR), Yellow (stagnant), Red (declining), Gray (no data)
- Last session date
- Cards sorted by: warnings > recent activity > no data

Health indicator derived from `/metrics/diagnostics` findings — zero backend changes needed.

#### Level 1: Element Detail (`/progress?element=axel`)

- Breadcrumb: "< Прогресс / Аксель"
- Top 3 diagnostic alerts (inline)
- 4 metric cards (2×2 grid): value + trend arrow + mini sparkline
  - Smart selection: warnings first, then PRs, then primary metric
- Primary trend chart (pre-selected metric: `max_height` for jumps, `edge_change_smoothness` for three_turn)
- Period selector on primary chart only
- "Все метрики (9) ▾" expandable link

#### Level 2: Metric Deep Dive (`/progress?element=axel&metric=airtime`)

- Metric header + unit + direction indicator
- Full TrendChart
- PR section with session link
- Specific diagnostic finding
- Reference range with position indicator
- Compare periods toggle (overlay previous period as dashed line)

**Cognitive load reduction:**

| Metric | Before | After |
|--------|--------|-------|
| Decision points on load | 14-16 | 0 (just scan cards) |
| Element choices | 8 buttons simultaneously | 8 cards with health context |
| Metric choices | 9-dropdown always visible | 4 pre-selected cards at L1 |
| Steps to specific trend | 3 simultaneous choices | 2 sequential taps |

### 3.3 Compare Page: Full State Coverage

**Current:** No loading, empty, or error states. Dead end if <2 sessions.

**Proposed:**
- Explicit conditional rendering with `usePageStatus` hook
- Empty state 1 (no sessions): "Нет сессий для сравнения" + upload CTA
- Empty state 2 (sessions exist, none selected): "Выберите две сессии" with guidance
- Session pickers with search
- Entry from Session Detail Export tab (auto-fills `left` param)
- `/compare` remains standalone route for arbitrary comparison

---

## 4. Unified State Patterns

### 4.1 `usePageStatus` Hook (NOT a render-prop component)

The spec originally proposed a `<PageState>` render-prop component. **This is the wrong abstraction** because most pages have multiple queries (Connections: 2 queries, Students: 2 queries, Profile: 3+ queries). A single-query wrapper doesn't compose.

**Instead, use explicit conditional rendering** with a `usePageStatus` helper hook:

```tsx
// lib/hooks/use-page-status.ts
export function usePageStatus(queries: Array<{ status: string }>) {
  const isLoading = queries.some(q => q.status === "pending")
  const isError = queries.some(q => q.status === "error")
  const refetch = () => queries.forEach(q => 'refetch' in q && (q as any).refetch())
  return { isLoading, isError, refetch }
}
```

Pages use it explicitly:
```tsx
const conn = useConnections()
const pending = usePendingConnections()
const { isLoading, isError, refetch } = usePageStatus([conn, pending])

if (isLoading) return <SkeletonConnection />
if (isError) return <ErrorState onRetry={refetch} />
if (!conn.data?.connections.length && !pending.data?.connections.length) return <EmptyState ... />
return <ConnectionsList ... />
```

**Why this over `<PageState>`:** Handles multi-query pages, no hidden magic, easy to customize per page, type-safe.

### 4.2 `<ErrorState>` Component

```tsx
<ErrorState
  title="Что-то пошло не так"
  message="Не удалось загрузить данные. Проверьте подключение."
  onRetry={refetch}
  supportHref="https://t.me/xpos587"
/>
```

### 4.3 Missing State Specifications

| Page | Add Loading | Add Empty | Add Error |
|------|-------------|-----------|-----------|
| Connections | SkeletonConnection | (exists) | ErrorState + retry |
| Compare | SkeletonCompare | "Нет сессий" / "Выберите две" | ErrorState + retry |
| Students/[id] | SkeletonChart + SkeletonCard | (exists) | ErrorState + retry |
| Profile | SkeletonProfile | "Профиль не загружен" | ErrorState + reload |
| Dashboard | Replace bare "Loading..." with SkeletonCard | (exists) | ErrorState + retry |
| Choreography | Replace bare "Loading..." with SkeletonCard | (exists) | ErrorState + retry |
| Sessions/[id] | (exists) | "Сессия не найдена" + CTA back to feed | (exists) |
| Feed | (exists) | Add "no matching sessions" for filter-empty | ErrorState + retry |

**Skeleton conventions:** Use `border-border bg-background` containers with `bg-muted` inner bars. Do NOT use shadcn's `bg-secondary` — it conflicts with existing custom skeletons.

### 4.4 Session Processing Enhancement

**Stale detection in SessionStatus:**
- After 3 min running: "Анализ занимает дольше обычного. Это нормально для длинных видео."
- After 10 min: "Анализ слишком долгий." + retry/cancel options
- Failed state: keep original video playable

**Processing state is business state, not query state:** `usePageStatus` handles React Query lifecycle. The sticky banner for session processing is a separate UI concern — don't conflate with API loading states.

### 4.5 Global Error Handling

**QueryCache.onError** in providers.tsx: toast for non-401 API errors (currently silently swallowed). Only toast for initial fetches (not background refetches), to avoid noise.

### 4.6 Filter-Empty vs Data-Empty

Feed and Progress pages must distinguish:
- **Data-empty:** "No sessions at all" → EmptyState with upload CTA
- **Filter-empty:** "No sessions match your filter" → "Попробуйте изменить фильтры" with clear-filters button

---

## 5. Onboarding Optimization

### 5.1 Current Path (8-12 steps, 4-10 min)

```
Landing → Register (4 fields) → Email Verify (BLOCKER + re-login required) → Login (re-enter credentials)
→ OnboardingGate → Role Select → Tour → Empty Feed → Upload → Processing → Results
```

**Key problems:**
- After email verify, user must manually click to `/login` and re-enter credentials — no auto-login
- `OnboardingGate` blocks ALL app access until role is selected
- No demo session — user sees empty feed immediately

### 5.2 Optimized Path (~30-60 seconds to aha)

```
Landing → Register (2 fields: email + password with show/hide) → Feed (with demo session) → Tap demo → AHA
  ↓ (persistent banner: "Подтвердите email для загрузки видео")
  → User taps "Загрузить видео" → Inline verify modal (not page redirect) → Upload
```

**Realistic timing:** ~30-60 seconds (including Next.js hydrate + auth fetch + video load), not "10 seconds."

**Key changes:**

| Change | Time Saved | Risk Level |
|--------|-----------|------------|
| Pre-loaded demo session | 4-10 min → 30-60 sec | **High** (requires backend) |
| Inline email verify (not redirect) | 1-3 min | Medium (backend audit needed) |
| 2-field registration (defer name) | 10-15 sec | Low |
| Skip onboarding before first value | 15-30 sec | Medium (nav needs default) |
| Post-first-upload onboarding celebration | 0 (better context) | Low |
| Smart defaults (language, timezone) | 5 sec | Low |

### 5.3 Email Verification: Inline Modal, NOT Gate Removal

**Security constraint:** Upload/create endpoints require `VerifiedUser` on the backend. Removing this guard would allow GPU/R2 abuse (unverified users uploading videos at $0.50-2.00 compute cost per upload).

**Proposed approach:**
1. Registration auto-logs in (no redirect to `/verify-email`)
2. Unverified users see the full app shell (feed, progress, etc.) with a persistent banner
3. **Upload remains gated on verification** — when unverified user taps "Загрузить видео", show inline verify modal (not page redirect)
4. Verified email required for: upload, connections, sharing, delete
5. NOT required for: viewing demo session, viewing own analysis, profile

This preserves GPU cost protection while eliminating the dead-end verify page.

### 5.4 Demo Session Implementation

**Frontend-only MVP (recommended for Phase 3):**
- Hardcode a "demo session" tile in the feed that links to `/sessions/demo-axel`
- `/sessions/demo-axel` renders a static page with pre-computed analysis data (no backend query)
- Demo data served as **static JSON** (NOT bundled in JS — fetch from `/public/demo/session.json` to keep bundle size lean)
- Demo video URL points to a public R2 object (no auth needed for this one asset)
- "Демо" badge on session tile + persistent "Загрузить своё видео" CTA on demo detail
- Avoids: DB migration, R2 asset duplication, GDPR concerns

**Full backend version (future):**
- Add `is_demo` flag to sessions table
- On user creation, link to a shared pre-analyzed session
- Requires: DB migration, demo asset management, GDPR consent for demo video subject

**Recommendation:** Start with frontend-only MVP. It delivers the same user value (seeing analysis in <60 seconds) with zero backend risk.

### 5.5 Onboarding as Celebration

- Role selection shown after first analysis completes (not as gate)
- Default nav: universal 4-item (Записи, Прогресс, Программа, Профиль) works for all roles
- Coach features surface via empty state CTAs and contextual tabs
- TourSlider shown post-analysis with role-specific content

### 5.6 Coach Flow

- Coach sees same demo session → aha
- Then: prominent "Пригласите учеников" banner on empty dashboard
- **Coach Sandbox:** Pre-populate dashboard with 2 fictitious students + sample sessions so coach sees value before inviting real students. **Frontend-only MVP** — mock data in component, no DB rows. Avoids GDPR concerns with real-looking names.
- Connections: inline invite form (fix `href="#"` bug)
- Coach uses view switcher on Progress/Dashboard pages (see Section 2.2)

### 5.7 Missing Onboarding Considerations

**After demo session CTA:** Demo session detail needs a persistent "Загрузить своё видео" banner/button. Currently no next-step action after viewing demo.

**Users without video:** Add "У меня нет видео" path on empty feed → "Как снимать видео" guide (camera angle, lighting, distance).

**Mobile → Web deep link:** No deep link exists for Android → Web upload. Add `/upload?source=android` with instructions, or generate pairing code for direct upload.

**Show/hide password toggle:** Required when removing confirm_password. Add eye icon toggle to `FormField` password inputs.

### 5.8 Empty State Russian Copy

| Page | Title | Description | CTA |
|------|-------|-------------|-----|
| Feed (data-empty) | "Пока нет сессий" | "Загрузите первое видео, чтобы получить биомеханический анализ." | "Загрузить видео" → `/upload` |
| Feed (filter-empty) | "Ничего не найдено" | "Попробуйте изменить фильтры или сбросить их." | "Сбросить фильтры" |
| Progress | "Пока нет данных" | "Загрузите видео тренировок, чтобы отслеживать динамику." | "Загрузить видео" → `/upload` |
| Dashboard (coach) | "Нет учеников" | "Пригласите учеников по email — вы увидите их сессии и прогресс." | "Пригласить" → inline form |
| Connections | "Нет связей" | "Пригласите тренера или ученика, чтобы начать совместную работу." | "Пригласить" → inline form |
| Compare (no sessions) | "Нет сессий для сравнения" | "Загрузите хотя бы два видео, чтобы сравнить результаты." | "Загрузить видео" → `/upload` |
| Compare (none selected) | "Выберите две сессии" | "Выберите сессии слева и справа для сравнения." | — |

---

## 6. Migration Plan

### Phase 1 — Low-Risk (components, states, fixes)

- [ ] Create `usePageStatus` hook + `<ErrorState>` component
- [ ] Create `<SkeletonConnection>`, `<SkeletonCompare>`, `<SkeletonProfile>`, `<SkeletonStudent>` components
- [ ] Add explicit loading/error/empty handling to: Connections, Compare, Students/[id], Profile, Dashboard, Choreography, Feed (filter-empty)
- [ ] Replace bare "Loading..." with proper skeletons on Dashboard, Choreography
- [ ] Fix Connections empty state `href="#"` → inline invite form
- [ ] Add "not found" CTA on Sessions/[id] (link back to feed)
- [ ] Add "failed video playback" state — keep original `video_url` playable when processing fails
- [ ] Fix Diagnostics heading ("Рекомендации" → "Диагностика")
- [ ] Localize metric names in session cards via `registry?.label_ru`
- [ ] Add Russian + English translations for new empty/error states to `ru.json` AND `en.json`
- [ ] Add filter-empty state to Feed ("No matching sessions" + clear filters)
- [ ] Add filter-empty state to Progress ("Нет данных по этому элементу" + clear)
- [ ] Add show/hide password toggle to `FormField`
- [ ] Add skip-nav link ("Перейти к содержимому") for WCAG 2.4.1
- [ ] Add `focus-visible:ring-2 ring-ring` to all interactive elements
- [ ] Fix nested `role="button"` on VideoWithSkeleton (WCAG 4.1.2)
- [ ] Add `aria-live="polite"` region for SSE processing status updates
- [ ] Add `role="status"` on empty state containers
- [ ] Add `CurrentUser` auth to `detect.py` and `process.py` routes (P0 security)
- [ ] Add rate limiting middleware for uploads, presign, sessions endpoints

### Phase 2 — Structural (page redesigns, nav)

- [ ] Rename nav item: Planner → Программа (only this rename is clearly better)
- [ ] CSS spike: center FAB with `safe-area-inset-bottom` — if fails, fall back to content-area FAB
- [ ] Implement universal 4-item nav + center FAB (Записи, Прогресс, Программа, Профиль)
- [ ] Add conditional Dashboard nav item for coaches (keep existing `hasStudents` logic + role check)
- [ ] Move Connections, Settings under Profile submenu
- [ ] Session detail: implement `[...v]` menu (Share, Compare, Print, Delete)
- [ ] Session detail: implement 3-tab layout (Overview/Details/Export) with URL param `?tab=` via `replaceState`
- [ ] Session detail: sticky processing banner instead of full-page replacement
- [ ] Add `?element=` and `?metric=` query params to Progress page
- [ ] Keep `/compare` as standalone route; add "Сравнить" entry point from session detail Export tab
- [ ] Add `GET /metrics/element-summary` batched endpoint for Progress L1
- [ ] Add `queryClient.invalidateQueries({ queryKey: ["trend"] })` and `["diagnostics"]` to upload success handler
- [ ] Gate polling on `hasProcessingSessions` flag
- [ ] Coach view switcher on Progress and Dashboard pages (Мой прогресс ↔ Ученики)
- [ ] PhaseTimeline: add keyboard navigation (arrow keys) + `aria-valuenow`/`aria-valuemax`
- [ ] 3D viewer: add keyboard orbit controls (WASD + QE) + `aria-label`
- [ ] Health indicators: add icons alongside color (✓/⚠/✗) for WCAG 1.4.1

### Phase 3 — Flow Optimization (onboarding, progressive disclosure)

- [ ] Inline email verify modal (not redirect) — backend `VerifiedUser` already matches, frontend-only change
- [ ] Demo session: static JSON at `/public/demo/session.json`, demo video from public R2 link
- [ ] Demo session detail: persistent "Демо" badge + "Загрузить своё видео" CTA
- [ ] Move onboarding to post-first-analysis celebration
- [ ] Registration: 2 fields (defer display name), remove confirm_password
- [ ] Progress page: implement Level 0 (element cards) and Level 1 (element detail with metric cards)
- [ ] Progress page: implement Level 2 (metric deep dive with reference range)
- [ ] Add stale detection to SessionStatus (3 min / 10 min thresholds)
- [ ] Global QueryCache.onError toast for non-401 errors
- [ ] Coach Sandbox: frontend mock data (2 fictitious students), no DB rows
- [ ] Contextual tour on session detail (first 1-3 visits, localStorage counter)
- [ ] "У меня нет видео" path on empty feed → "Как снимать видео" guide
- [ ] Mobile deep link: `/upload?source=android` with instructions
- [ ] Profile page: lift queries from sub-components to page level for proper state coverage (estimated 2-3x current complexity)
- [ ] `prefers-reduced-motion`: disable 3D viewer auto-rotation
- [ ] Audit touch targets for 44×44px minimum (WCAG 2.5.8)
- [ ] Audit `text-muted-foreground` contrast ratios (WCAG 1.4.3)

---

## 7. Open Questions (Resolved and Remaining)

### Resolved

| # | Question | Resolution |
|---|----------|-------------|
| Q4 | Compare standalone vs inline? | **Both**: Keep `/compare` route + add entry from session detail Export tab |
| Q5 | Coach dashboard vs Feed? | Dashboard remains accessible via Profile/empty-state CTA. Coaches see Feed for their own sessions. |
| Q6 | Email verification threshold? | **Upload, connections, sharing, delete require verification.** Viewing (including demo) does not. |
| Q7 | Coach features as tabs or switcher? | **View switcher** (like ClassDojo) — same-place different lens, not separate sections |
| Q8 | Demo session data delivery? | **Static JSON from `/public/demo/session.json`**, NOT bundled in JS |
| Q9 | Backend changes for email verify? | **Zero backend changes.** `VerifiedUser` map already matches proposed policy. Frontend-only change. |

### Remaining

| # | Question | Context |
|---|----------|---------|
| Q1 | Demo session content | Which element/video? Triple axel is impressive but may set unrealistic expectations. Start with a clean single axel? |
| Q2 | Metric card count at L1 | 4 cards (2×2) on mobile, 6 (2×3) on desktop? Responsive grid? |
| Q3 | Bottom dock center button | Needs CSS spike for absolute-positioned center FAB with `safe-area-inset-bottom`. Technical spike recommended. |
| Q4 | Role switching UI | No UI to change role post-onboarding. Should `/settings` have a role switch? Or detect from behavior? |
| Q5 | Coach sandbox data | Pre-populate with real-looking fictitious names (Алексей, Мария) or anonymized real data? GDPR implications? |
| Q6 | Mobile deep link | Android → Web pairing mechanism. QR code? Direct API upload with JWT? Requires Android app changes. |
| Q7 | Export tab vs overflow menu | Export as 3rd tab has no competitive precedent in sports apps. User test needed; fallback = overflow menu on Overview |
| Q8 | Center FAB vs content-area FAB | Center FAB may cause accessibility/safe-area issues. CSS spike first; fallback = top-of-feed banner |
| Q9 | 3-level progressive disclosure depth | L0→L1→L2 may be excessive for some users. Consider collapsing L2 into L1 with expand/collapse |
| Q10 | Profile page state coverage complexity | Lifting queries from sub-components to page level is 2-3x current complexity. Worth it? Or keep sub-component states? |
| Q11 | SSE `/process/{task_id}/stream` auth | Currently no auth — any user can subscribe to any task. Fix in Phase 1 or Phase 2? |

---

## 8. Accessibility (WCAG 2.1 AA)

**Current state:** 0/40 — app fails virtually all WCAG criteria.

### Critical Issues (P0 — must fix before any restructure ships)

| Issue | WCAG Criterion | Fix |
|-------|---------------|-----|
| Nested `role="button"` on video container | 4.1.2 Name/Role/Value | Remove outer `role`, apply to actual interactive element only |
| PhaseTimeline not keyboard operable | 2.1.1 Keyboard | Add `tabIndex`, arrow-key navigation, `aria-valuenow`/`aria-valuemax` |
| 3D skeleton viewer mouse-only | 2.1.1 Keyboard | Add orbit controls via keyboard (WASD + QE), `aria-label` describing view |
| Color-only health indicators (green/yellow/red) | 1.4.1 Use of Color | Add icons/text: ✓ (improving), ⚠ (stagnant), ✗ (declining) |
| No captions/transcript on video | 1.2.2 Captions | Add SRT/VTT support for coaching commentary (future); for now, `aria-label` describing video content |

### Important Issues (P1 — same release as restructure)

| Issue | WCAG Criterion | Fix |
|-------|---------------|-----|
| No skip-nav link | 2.4.1 Bypass Blocks | Add "Перейти к содержимому" skip link |
| Tab navigation has no visible focus indicator | 2.4.7 Focus Visible | Use `focus-visible:ring-2 ring-ring` on all interactive elements |
| Session cards have no heading structure | 1.3.1 Info and Relationships | Use `h2` for session name, `h3` for metrics within cards |
| Form inputs missing `aria-describedby` | 3.3.2 Labels or Instructions | Link error messages via `aria-describedby` |
| Dynamic content (SSE processing) not announced | 4.1.3 Status Messages | Use `aria-live="polite"` region for processing status updates |
| Empty states not announced to screen readers | 4.1.3 Status Messages | Use `role="status"` on empty state containers |

### Enhancement (P2 — post-restructure)

| Issue | WCAG Criterion | Fix |
|-------|---------------|-----|
| No reduced-motion alternative for 3D viewer | 2.3.3 Animation from Interactions | Respect `prefers-reduced-motion`, disable auto-rotation |
| Touch targets < 44×44px on some mobile elements | 2.5.8 Target Size | Audit and enlarge small touch targets |
| Color contrast failures on muted text | 1.4.3 Contrast | Audit all `text-muted-foreground` against backgrounds |

---

## 9. Performance Considerations

### API Batching

**Problem:** Progress L1 (`/progress?element=axel`) fires 5-6 parallel API calls: `useTrend`, `useDiagnostics`, `useMetricRegistry`, `usePRs`, plus session queries. Waterfall on slow connections.

**Solution:** Add `GET /metrics/element-summary?element=axel` batched endpoint returning trend, diagnostics, registry, and PRs in single response. Frontend uses this at L1; individual endpoints remain for L2 deep dive.

**Phase:** Phase 2 (Progress page redesign). Backend change required.

### Cache Invalidation

**Missing invalidation:** When a new session is created, `["trend"]` and `["diagnostics"]` query caches become stale. Currently `useMutation` for upload only invalidates `["sessions"]`.

**Fix:** Add `queryClient.invalidateQueries({ queryKey: ["trend"] })` and `["diagnostics"]` to upload success handler.

### Tab State Management

Use `window.history.replaceState` for `?tab=overview|details|export`, not `router.push`. Prevents back-button spam (each tab switch would otherwise push a history entry).

### 3D Viewer Gating

ThreeJSkeletonViewer is already `React.lazy` code-split. Tab gating (only mount on Details tab) provides marginal additional benefit — avoids GPU context creation when not visible. Keep it for battery savings on mobile.

### Polling Optimization

**Current:** `useSession` polls every 5s for `status === "processing"`. If multiple sessions are processing, this creates N parallel polls.

**Fix:** Gate global polling on `hasProcessingSessions` flag. Single interval checks processing status; individual session polls only for the active session detail page.

### Demo Session Data

Demo session analysis must be **static JSON** served from `/public/demo/session.json`, NOT bundled in the JavaScript bundle. Video URL can be a public R2 link. This keeps bundle size unchanged.

---

## 10. Security

### Critical: Unauthenticated Endpoints

**`/detect` route (`backend/app/routes/detect.py`):** NO AUTHENTICATION. Anyone can enqueue person detection jobs.
**`/process` route (`backend/app/routes/process.py`):** NO AUTHENTICATION. Anyone can enqueue GPU video processing jobs.

**Impact:** GPU cost abuse ($0.50-2.00 per video), R2 storage abuse, potential DDoS vector.

**Fix:** Add `CurrentUser` dependency (minimum) to both routes. Consider `VerifiedUser` to match upload policy.

**SSE endpoint `/process/{task_id}/stream`:** Also has NO AUTH. Any user can subscribe to any task's status stream. Add `CurrentUser` + verify task belongs to user.

### Rate Limiting

No rate limits exist on: `POST /sessions`, `POST /uploads/presign`, `POST /uploads/complete`. These are the most expensive endpoints (GPU + storage).

**Fix:** Add rate limiting middleware (e.g., `slowapi`) with:
- Upload: 5/hour per user
- Sessions: 20/hour per user
- Presign: 10/hour per user

### Email Verification Policy

Backend `VerifiedUser` map already matches spec's proposed policy:
- Upload, connections, sharing, delete → require `VerifiedUser` ✓
- Viewing sessions, progress, profile → `CurrentUser` only ✓

**Zero backend changes needed** for the inline verify modal. Frontend just needs to call `POST /auth/verify-email` and handle response in-context.

---

## 11. Before/After Comparison

### Navigation

| Aspect | Before | After |
|--------|--------|-------|
| Primary nav items | 5-6 (conditional Dashboard) | 4 universal + center FAB + conditional Dashboard |
| Nav depth | 2 levels | 2 levels (3 with Profile submenu) |
| Dead ends | Compare orphan, Connections `href="#"`, Email verify | All eliminated |
| Labels | Already Russian via `ru.json`, but route paths English | Russian labels + metric localization |
| Multi-role | Single role enforced, no switching | Universal nav + view switcher on coach pages |

### Flows

| Task | Before (steps) | After (steps) | Reduction |
|------|----------------|---------------|-----------|
| Sign up → first aha | 8-12 (with re-login bug) | 3-4 (with demo) | -65% |
| View session analysis | 1 (but 4-5 actions visible) | 1 (progressive tabs) | -70% visual clutter |
| Find specific metric trend | 3 simultaneous choices | 2 sequential taps | -66% cognitive load |
| Compare two sessions | Navigate to /compare (orphan) + manual session ID | Action from session detail → auto-fill left | -50% steps |
| Compare any two sessions | Know URL or find /compare | Still available at /compare | Preserved |

### State Coverage

| Aspect | Before | After |
|--------|--------|-------|
| Pages with loading states | 4/10 | 10/10 |
| Pages with error states | 2/10 | 10/10 |
| Pages with empty states | 6/10 | 10/10 |
| Processing state | Full-page replacement | Sticky banner |

### Heuristic Score Target

| Heuristic | Before | After (target) | Delta |
|-----------|--------|-----------------|-------|
| H1: System Status | 2 | 3 | +1 |
| H2: Match Real World | 2 | 3 | +1 |
| H3: User Control | 1 | 3 | +2 |
| H4: Consistency | 2 | 3 | +1 |
| H5: Error Prevention | 1 | 3 | +2 |
| H6: Recognition | 1 | 3 | +2 |
| H7: Flexibility | 2 | 3 | +1 |
| H8: Minimalist | 2 | 3 | +1 |
| H9: Error Recovery | 1 | 4 | +3 |
| H10: Help | 1 | 2 | +1 |
| **Total** | **19** | **30** | **+11** |

### WCAG Score Target

| Category | Before | After (target) |
|----------|--------|-----------------|
| Perceivable | 0/12 | 6/12 (color + contrast + captions) |
| Operable | 0/12 | 8/12 (keyboard + focus + skip-nav) |
| Understandable | 0/8 | 6/8 (labels + error ID + status messages) |
| Robust | 0/8 | 4/8 (ARIA roles + name/role/value) |
| **Total** | **0/40** | **24/40** |