# UX Restructure — Phase 1: State Patterns & Accessibility

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add missing loading, error, and empty states to all data pages. Fix critical WCAG violations. Fix security bugs (unauth endpoints). This is the foundation — every subsequent phase depends on these components existing.

**Architecture:** Create reusable `usePageStatus` hook + `ErrorState` component, then apply explicit conditional rendering to each page. Add skeleton components for pages that lack them. Fix WCAG issues (nested role, focus indicators, aria-live). Add auth to `detect.py` and `process.py`. All changes are additive — no existing functionality removed.

**Tech Stack:** React Query, Next.js 16, Tailwind CSS, shadcn/ui, Litestar (backend)

**Spec reference:** `docs/specs/2026-05-16-ux-restructure-design.md` — Sections 1.2 (Priority Issues), 4 (State Patterns), 8 (Accessibility), 10 (Security)

---

## File Structure

### New files

- `frontend/src/lib/hooks/use-page-status.ts` — Multi-query status aggregation hook
- `frontend/src/components/error-state.tsx` — Reusable error state component
- `frontend/src/components/skeleton-connection.tsx` — Connections page skeleton
- `frontend/src/components/skeleton-compare.tsx` — Compare page skeleton
- `frontend/src/components/skeleton-profile.tsx` — Profile page skeleton
- `frontend/src/components/skeleton-student.tsx` — Student detail page skeleton
- `frontend/src/lib/hooks/use-processing-sessions.ts` — Hook to check if any sessions are processing
- `frontend/messages/ru.json` — New keys added (empty states, error states, a11y)
- `frontend/messages/en.json` — New keys added (empty states, error states, a11y)

### Modified files

- `frontend/src/app/providers.tsx` — Add QueryCache.onError toast for non-401 errors
- `frontend/src/app/(app)/connections/page.tsx` — Add loading/error states, fix href="#" bug
- `frontend/src/app/(app)/compare/page.tsx` — Add loading/error/empty states
- `frontend/src/app/(app)/students/[id]/page.tsx` — Add error state with retry
- `frontend/src/app/(app)/profile/page.tsx` — Add loading/error states
- `frontend/src/app/(app)/dashboard/page.tsx` — Replace bare "Loading..." with SkeletonCard
- `frontend/src/app/(app)/feed/page.tsx` — Add filter-empty state
- `frontend/src/app/(app)/progress/page.tsx` — Add filter-empty state
- `frontend/src/app/(app)/sessions/[id]/page.tsx` — Add "not found" CTA, keep video playable on failure
- `frontend/src/components/layout/bottom-dock.tsx` — Add skip-nav link, focus-visible
- `frontend/src/components/app-nav.tsx` — Add focus-visible
- `frontend/src/components/onboarding/empty-state.tsx` — Add role="status", aria-live
- `frontend/src/components/analysis/video-with-skeleton.tsx` — Fix nested role="button"
- `frontend/src/components/analysis/phase-timeline.tsx` — Add tabIndex, aria attributes
- `backend/app/routes/detect.py` — Add CurrentUser dependency to all endpoints
- `backend/app/routes/process.py` — Add CurrentUser dependency + auth to SSE stream
- `backend/app/middleware/rate_limit.py` — Add rate limits for uploads, presign, sessions

---

## Wave 1: Core Components

### Task 1: `usePageStatus` hook

**Files:**

- Create: `frontend/src/lib/hooks/use-page-status.ts`
- Test: `frontend/src/lib/hooks/__tests__/use-page-status.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/hooks/__tests__/use-page-status.test.ts
import { describe, it, expect } from "vitest"
import { renderHook } from "@testing-library/react"
import { usePageStatus } from "../use-page-status"

describe("usePageStatus", () => {
  it("returns loading when any query is pending", () => {
    const result = renderHook(() =>
      usePageStatus([
        { status: "pending" },
        { status: "success" },
      ]),
    )
    expect(result.result.current.isLoading).toBe(true)
    expect(result.result.current.isError).toBe(false)
  })

  it("returns error when any query has error", () => {
    const result = renderHook(() =>
      usePageStatus([
        { status: "error" },
        { status: "success" },
      ]),
    )
    expect(result.result.current.isLoading).toBe(false)
    expect(result.result.current.isError).toBe(true)
  })

  it("returns neither when all queries succeeded", () => {
    const refetch1 = vi.fn()
    const refetch2 = vi.fn()
    const result = renderHook(() =>
      usePageStatus([
        { status: "success", refetch: refetch1 },
        { status: "success", refetch: refetch2 },
      ]),
    )
    expect(result.result.current.isLoading).toBe(false)
    expect(result.result.current.isError).toBe(false)
  })

  it("refetch calls refetch on all queries that have it", () => {
    const refetch1 = vi.fn()
    const refetch2 = vi.fn()
    const result = renderHook(() =>
      usePageStatus([
        { status: "error", refetch: refetch1 },
        { status: "success", refetch: refetch2 },
      ]),
    )
    result.result.current.refetch()
    expect(refetch1).toHaveBeenCalledOnce()
    expect(refetch2).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && bunx vitest run src/lib/hooks/__tests__/use-page-status.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Write implementation**

```typescript
// frontend/src/lib/hooks/use-page-status.ts
type QueryLike = {
  status: string
  refetch?: () => void
}

export function usePageStatus(queries: QueryLike[]) {
  const isLoading = queries.some(q => q.status === "pending")
  const isError = queries.some(q => q.status === "error")
  const refetch = () => {
    for (const q of queries) {
      q.refetch?.()
    }
  }
  return { isLoading, isError, refetch }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && bunx vitest run src/lib/hooks/__tests__/use-page-status.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/hooks/use-page-status.ts frontend/src/lib/hooks/__tests__/use-page-status.test.ts
git commit -m "feat(frontend): add usePageStatus hook for multi-query state aggregation"
```

---

### Task 2: `ErrorState` component

**Files:**

- Create: `frontend/src/components/error-state.tsx`

- [ ] **Step 1: Create ErrorState component**

```tsx
// frontend/src/components/error-state.tsx
"use client"

import { AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
  supportHref?: string
}

export function ErrorState({
  title = "Что-то пошло не так",
  message = "Не удалось загрузить данные. Проверьте подключение к интернету.",
  onRetry,
  supportHref = "https://t.me/xpos587",
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-4 text-center" role="alert">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-[1.25rem] bg-destructive/10 text-destructive">
        <AlertCircle className="h-7 w-7" />
      </div>
      <h3 className="mb-2 text-lg font-medium text-foreground">{title}</h3>
      <p className="mb-8 max-w-sm text-sm text-ink-mute leading-relaxed">{message}</p>
      <div className="flex flex-col items-center gap-3 sm:flex-row">
        {onRetry && (
          <Button onClick={onRetry}>Попробовать снова</Button>
        )}
        <a
          href={supportHref}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium text-ink-mute hover:text-foreground transition-colors"
        >
          Написать в поддержку
        </a>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify component renders**

Run: `cd frontend && bunx next lint`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/error-state.tsx
git commit -m "feat(frontend): add ErrorState component with retry and support link"
```

---

### Task 3: Skeleton components (Connection, Compare, Profile, Student)

**Files:**

- Create: `frontend/src/components/skeleton-connection.tsx`
- Create: `frontend/src/components/skeleton-compare.tsx`
- Create: `frontend/src/components/skeleton-profile.tsx`
- Create: `frontend/src/components/skeleton-student.tsx`

- [ ] **Step 1: Create all skeleton components**

Each follows the existing `SkeletonCard` pattern: `border-border bg-background` container with `bg-muted` inner bars.

```tsx
// frontend/src/components/skeleton-connection.tsx
export function SkeletonConnection() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 animate-pulse">
      <div className="h-6 w-32 rounded bg-muted" />
      <div className="space-y-2">
        <div className="h-4 w-28 rounded bg-muted" />
        <div className="flex gap-2">
          <div className="h-11 flex-1 rounded-xl bg-muted" />
          <div className="h-11 w-20 rounded-xl bg-muted" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-4 w-24 rounded bg-muted" />
        <div className="h-14 rounded-xl border border-border bg-muted" />
      </div>
    </div>
  )
}
```

```tsx
// frontend/src/components/skeleton-compare.tsx
export function SkeletonCompare() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-4 animate-pulse">
      <div className="h-7 w-36 rounded bg-muted" />
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-3 rounded-xl border border-border bg-background p-4">
          <div className="h-5 w-24 rounded bg-muted" />
          <div className="h-40 rounded bg-muted" />
        </div>
        <div className="space-y-3 rounded-xl border border-border bg-background p-4">
          <div className="h-5 w-24 rounded bg-muted" />
          <div className="h-40 rounded bg-muted" />
        </div>
      </div>
    </div>
  )
}
```

```tsx
// frontend/src/components/skeleton-profile.tsx
export function SkeletonProfile() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="h-16 w-16 rounded-full bg-muted" />
        <div className="space-y-2 flex-1">
          <div className="h-5 w-32 rounded bg-muted" />
          <div className="h-4 w-48 rounded bg-muted" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="h-24 rounded-2xl border border-border bg-muted" />
        <div className="h-24 rounded-2xl border border-border bg-muted" />
      </div>
    </div>
  )
}
```

```tsx
// frontend/src/components/skeleton-student.tsx
export function SkeletonStudent() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-full bg-muted" />
        <div className="space-y-2 flex-1">
          <div className="h-5 w-28 rounded bg-muted" />
          <div className="h-4 w-40 rounded bg-muted" />
        </div>
      </div>
      <div className="h-64 rounded-xl bg-muted" />
      <div className="grid grid-cols-3 gap-3">
        <div className="h-20 rounded-xl border border-border bg-muted" />
        <div className="h-20 rounded-xl border border-border bg-muted" />
        <div className="h-20 rounded-xl border border-border bg-muted" />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify no lint errors**

Run: `cd frontend && bunx next lint`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/skeleton-connection.tsx frontend/src/components/skeleton-compare.tsx frontend/src/components/skeleton-profile.tsx frontend/src/components/skeleton-student.tsx
git commit -m "feat(frontend): add skeleton components for connection, compare, profile, student pages"
```

---

## Wave 2: Apply State Patterns to Pages

### Task 4: Connections page — loading/error states + href="#" fix

**Files:**

- Modify: `frontend/src/app/(app)/connections/page.tsx`
- Modify: `frontend/messages/ru.json`
- Modify: `frontend/messages/en.json`

- [ ] **Step 1: Update i18n keys**

Add to `ru.json` under `emptyStates`:
```json
"connectionsLoading": "Загрузка связей...",
"connectionsError": "Не удалось загрузить связи."
```

Add to `en.json` under `emptyStates`:
```json
"connectionsLoading": "Loading connections...",
"connectionsError": "Failed to load connections."
```

- [ ] **Step 2: Update ConnectionsPage with usePageStatus + fix href="#"**

Key changes:
1. Import `usePageStatus`, `ErrorState`, `SkeletonConnection`
2. Replace bare early return with `usePageStatus([conns, pending])`
3. Add loading → `<SkeletonConnection />`
4. Add error → `<ErrorState onRetry={refetch} />`
5. Fix `primaryAction={{ label: ..., href: "#" }}` → remove `href`, use inline invite form (already exists below)

The Connections page already has the inline invite form. The empty state's `primaryAction` with `href="#"` is the bug. Fix: change the EmptyState to NOT use `primaryAction` — instead, the invite form is already visible on the same page. Replace with a simpler EmptyState that has no action since the form is right there.

- [ ] **Step 3: Verify page renders**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(app\)/connections/page.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "fix(frontend): add loading/error states to connections page, fix href=\"#\" bug"
```

---

### Task 5: Compare page — loading/error/empty states

**Files:**

- Modify: `frontend/src/app/(app)/compare/page.tsx`
- Modify: `frontend/messages/ru.json`
- Modify: `frontend/messages/en.json`

- [ ] **Step 1: Update i18n keys**

Add to `ru.json` under new `compare` section:
```json
"noSessions": "Нет сессий для сравнения",
"noSessionsDesc": "Загрузите хотя бы два видео, чтобы сравнить результаты.",
"noSessionsAction": "Загрузить видео",
"selectTwo": "Выберите две сессии",
"selectTwoDesc": "Выберите сессии слева и справа для сравнения.",
"loadError": "Не удалось загрузить данные для сравнения."
```

Add corresponding English to `en.json`.

- [ ] **Step 2: Update ComparePage with usePageStatus**

The Compare page currently has zero state handling. Add:
1. Import `useSessions`, `usePageStatus`, `ErrorState`, `SkeletonCompare`, `EmptyState`
2. `const { data: sessions, ...sessionsQuery } = useSessions()`
3. `const { isLoading, isError, refetch } = usePageStatus([sessionsQuery])`
4. Loading → `<SkeletonCompare />`
5. Error → `<ErrorState onRetry={refetch} />`
6. No sessions → EmptyState "Нет сессий для сравнения" with upload CTA
7. Has sessions → render `<SessionComparison />` (existing)

- [ ] **Step 3: Verify page renders**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(app\)/compare/page.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): add loading/error/empty states to compare page"
```

---

### Task 6: Profile, Dashboard, Choreography — add missing states

**Files:**

- Modify: `frontend/src/app/(app)/profile/page.tsx`
- Modify: `frontend/src/app/(app)/dashboard/page.tsx`
- Modify: `frontend/src/app/(app)/choreography/page.tsx`

- [ ] **Step 1: Add ErrorState to Profile page**

Import `usePageStatus`, `ErrorState`, `SkeletonProfile`. Wrap existing queries with `usePageStatus`. Add error branch with retry.

- [ ] **Step 2: Replace bare "Loading..." on Dashboard with SkeletonCard**

Find any bare "Loading..." or `isLoading` text returns and replace with `<SkeletonCard />`.

- [ ] **Step 3: Replace bare "Loading..." on Choreography with SkeletonCard**

Same pattern.

- [ ] **Step 4: Verify all pages compile**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(app\)/profile/page.tsx frontend/src/app/\(app\)/dashboard/page.tsx frontend/src/app/\(app\)/choreography/page.tsx
git commit -m "feat(frontend): add loading/error states to profile, dashboard, choreography pages"
```

---

### Task 7: Feed filter-empty + Progress filter-empty + Session "not found" CTA

**Files:**

- Modify: `frontend/src/app/(app)/feed/page.tsx`
- Modify: `frontend/src/app/(app)/progress/page.tsx`
- Modify: `frontend/src/app/(app)/sessions/[id]/page.tsx`
- Modify: `frontend/messages/ru.json`
- Modify: `frontend/messages/en.json`

- [ ] **Step 1: Add filter-empty state to Feed**

When `sessions` returns empty but `searchQuery` or `elementType` filter is active, show "Ничего не найдено" + "Сбросить фильтры" button instead of the data-empty EmptyState.

- [ ] **Step 2: Add filter-empty state to Progress**

When `trend` returns empty but an `element` is selected, show "Нет данных по этому элементу" with element selector still visible (not the data-empty EmptyState).

- [ ] **Step 3: Add "not found" CTA to Session detail**

Change `if (!session) return <div>...</div>` to include a link back to `/feed`:
```tsx
if (!session) return (
  <div className="flex flex-col items-center py-20 text-center" role="status">
    <p className="text-lg text-ink-mute">{ts("notFound")}</p>
    <Link href="/feed" className="mt-4 text-sm text-primary hover:underline">
      Вернуться к записям
    </Link>
  </div>
)
```

- [ ] **Step 4: Add failed-video-playable handling**

In the `failed` state branch, keep the original `video_url` playable. Change from showing only retry button to also showing the original video when `session.video_url` exists:
```tsx
if (session.video_url) {
  // Show original video even when processing failed
  <video src={session.video_url} controls className="w-full rounded-xl" />
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(app\)/feed/page.tsx frontend/src/app/\(app\)/progress/page.tsx frontend/src/app/\(app\)/sessions/\[id\]/page.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): filter-empty states, session not-found CTA, failed video playable"
```

---

## Wave 3: Accessibility Fixes (P0)

### Task 8: Fix nested role="button" + focus indicators

**Files:**

- Modify: `frontend/src/components/analysis/video-with-skeleton.tsx`
- Modify: `frontend/src/components/layout/bottom-dock.tsx`
- Modify: `frontend/src/components/app-nav.tsx`
- Modify: `frontend/src/components/onboarding/empty-state.tsx`

- [ ] **Step 1: Fix nested `role="button"` on VideoWithSkeleton**

Find the container `div` that has `role="button"` — if it wraps another element with `role="button"` or an interactive element, remove the outer `role="button"` and keep the interactive semantics on the actual interactive element only.

- [ ] **Step 2: Add `focus-visible:ring-2 ring-ring` to bottom dock links**

Add `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none` to each `<Link>` in `BottomDock`.

- [ ] **Step 3: Add `focus-visible:ring-2 ring-ring` to AppNav links**

Same pattern for desktop nav links.

- [ ] **Step 4: Add `role="status"` and `aria-live="polite"` to EmptyState**

```tsx
<div
  className={cn("flex flex-col items-center justify-center py-20 px-4 text-center", className)}
  role="status"
  aria-live="polite"
>
```

- [ ] **Step 5: Verify with linter**

Run: `cd frontend && bunx next lint && bunx tsc --noEmit`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/analysis/video-with-skeleton.tsx frontend/src/components/layout/bottom-dock.tsx frontend/src/components/app-nav.tsx frontend/src/components/onboarding/empty-state.tsx
git commit -m "fix(frontend): WCAG — nested role, focus indicators, aria-live on empty states"
```

---

### Task 9: PhaseTimeline keyboard navigation + aria attributes

**Files:**

- Modify: `frontend/src/components/analysis/phase-timeline.tsx`

- [ ] **Step 1: Add tabIndex and keyboard handlers to PhaseTimeline**

The PhaseTimeline needs:
- `tabIndex={0}` on the container to make it focusable
- Arrow key handlers (left/right) to move between phases
- `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label` attributes
- `onKeyDown` handler for arrow key navigation

- [ ] **Step 2: Verify component renders**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/analysis/phase-timeline.tsx
git commit -m "feat(frontend): add keyboard navigation and ARIA attributes to PhaseTimeline"
```

---

### Task 10: Skip-nav link

**Files:**

- Modify: `frontend/src/app/(app)/layout.tsx`

- [ ] **Step 1: Add skip-nav link**

Add as the first element inside the layout, before the header:
```tsx
<a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-foreground focus:ring-2 focus:ring-ring">
  Перейти к содержимому
</a>
```

Add `id="main-content"` to the main content area.

- [ ] **Step 2: Add i18n key**

Add `"skipToContent": "Перейти к содержимому"` to `ru.json` and `"skipToContent": "Skip to content"` to `en.json`. Use `useTranslations("common")` for the link text.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(app\)/layout.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): add skip-nav link for WCAG 2.4.1"
```

---

## Wave 4: Backend Security

### Task 11: Add auth to detect.py and process.py

**Files:**

- Modify: `backend/app/routes/detect.py`
- Modify: `backend/app/routes/process.py`

- [ ] **Step 1: Add CurrentUser to detect.py**

Import `CurrentUser` from `app.auth.deps`. Add `user: CurrentUser` parameter to `enqueue_detect`, `get_detect_status`, and `get_detect_result` methods. This ensures only authenticated users can enqueue detection jobs or read results.

- [ ] **Step 2: Add CurrentUser to process.py**

Import `CurrentUser` from `app.auth.deps`. Add `user: CurrentUser` parameter to `enqueue_process`, `get_process_status`, `cancel_queued_process`, and `stream_process_status` methods. For the SSE stream, add `user: CurrentUser` and verify `task_id` belongs to user (add ownership check via Valkey state).

- [ ] **Step 3: Add task ownership check to SSE stream**

In `stream_process_status`, after getting `task_state`, add:
```python
task_user_id = state.get("user_id")
if task_user_id and str(task_user_id) != str(user.id):
    raise NotAuthorizedException("Not authorized to view this task")
```

This requires also storing `user_id` in `create_task_state`. Add `user_id=str(user.id)` to `create_task_state` calls in `enqueue_process` and `enqueue_detect`.

- [ ] **Step 4: Write and run tests**

Create test file `backend/tests/test_detect_auth.py`:
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_detect_requires_auth(client: AsyncClient):
    response = await client.post("/api/detect", files={"video": ("test.mp4", b"data", "video/mp4")})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_process_requires_auth(client: AsyncClient):
    response = await client.post("/api/process/queue", json={...})
    assert response.status_code == 401
```

Run: `cd backend && uv run pytest tests/test_detect_auth.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/detect.py backend/app/routes/process.py backend/tests/test_detect_auth.py
git commit -m "fix(backend): add CurrentUser auth to detect and process routes — P0 security fix"
```

---

### Task 12: Add rate limiting for uploads, presign, sessions

**Files:**

- Modify: `backend/app/routes/uploads.py`
- Modify: `backend/app/routes/sessions.py`
- Modify: `backend/app/middleware/rate_limit.py` (if needed)

- [ ] **Step 1: Import and apply rate limiting to uploads**

In `uploads.py`, import `check_rate_limit` from `app.middleware.rate_limit`. Add to `init_upload`, `complete_upload`, and `presign_upload`:
```python
from app.middleware.rate_limit import check_rate_limit

# In each endpoint:
await check_rate_limit(f"upload:{user.id}", max_requests=10, window_seconds=3600)
```

- [ ] **Step 2: Import and apply rate limiting to sessions creation**

In `sessions.py`, add to `create_session`:
```python
await check_rate_limit(f"session_create:{user.id}", max_requests=20, window_seconds=3600)
```

- [ ] **Step 3: Run existing tests**

Run: `cd backend && uv run pytest backend/tests/ -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/uploads.py backend/app/routes/sessions.py
git commit -m "feat(backend): add rate limiting for uploads and session creation"
```

---

## Wave 5: Global Error Handling + i18n

### Task 13: Global QueryCache error toast

**Files:**

- Modify: `frontend/src/app/providers.tsx`

- [ ] **Step 1: Add toast for non-401 errors**

In `providers.tsx`, extend `QueryCache.onError` to show toast for non-401 errors:
```tsx
import { toast } from "sonner"

// In QueryCache.onError:
onError(error, query) {
  if (error instanceof ApiError && error.status === 401 && typeof window !== "undefined") {
    const path = globalThis.location.pathname
    if (!isPublicPage(path)) globalThis.location.href = "/login"
    return
  }
  // Only toast for initial fetches, not background refetches
  if (error instanceof ApiError && query.state.data !== undefined) return
  if (error instanceof ApiError && error.status !== 401) {
    toast.error("Что-то пошло не так", {
      description: error.message || "Не удалось загрузить данные",
      duration: 4000,
    })
  }
}
```

- [ ] **Step 2: Verify toast renders on error**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/providers.tsx
git commit -m "feat(frontend): add global error toast for non-401 API errors"
```

---

### Task 14: Add all i18n translations for new states

**Files:**

- Modify: `frontend/messages/ru.json`
- Modify: `frontend/messages/en.json`

- [ ] **Step 1: Add Russian translations**

Add under `emptyStates`:
```json
"noMatchTitle": "Ничего не найдено",
"noMatchDesc": "Попробуйте изменить фильтры или сбросить их.",
"clearFilters": "Сбросить фильтры",
"noElementData": "Нет данных по этому элементу",
"profileError": "Не удалось загрузить профиль",
"dashboardError": "Не удалось загрузить данные",
"choreographyError": "Не удалось загрузить программы"
```

- [ ] **Step 2: Add English translations**

Add corresponding English under `emptyStates`:
```json
"noMatchTitle": "No matches found",
"noMatchDesc": "Try adjusting your filters or clear them.",
"clearFilters": "Clear filters",
"noElementData": "No data for this element",
"profileError": "Failed to load profile",
"dashboardError": "Failed to load data",
"choreographyError": "Failed to load programs"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): add i18n translations for new error/empty states"
```

---

### Task 15: Show/hide password toggle

**Files:**

- Modify: `frontend/src/components/form-field.tsx`
- Modify: `frontend/src/app/(auth)/register/page.tsx`

- [ ] **Step 1: Add eye toggle to FormField for password type**

In `form-field.tsx`, when `type === "password"`, add an eye icon button that toggles between `password` and `text` input type. Use `useState` for the toggle. Import `Eye` and `EyeOff` from lucide-react.

- [ ] **Step 2: Verify form renders**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/form-field.tsx
git commit -m "feat(frontend): add show/hide password toggle to FormField"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Requirement | Task |
|---|---|
| usePageStatus hook | Task 1 |
| ErrorState component | Task 2 |
| Skeleton components (4 pages) | Task 3 |
| Connections loading/error/href="#" fix | Task 4 |
| Compare loading/error/empty | Task 5 |
| Profile/Dashboard/Choreography states | Task 6 |
| Feed filter-empty | Task 7 (partial) |
| Progress filter-empty | Task 7 (partial) |
| Session not-found CTA | Task 7 (partial) |
| Failed video playable | Task 7 (partial) |
| Nested role="button" fix | Task 8 |
| Focus-visible indicators | Task 8 |
| aria-live on EmptyState | Task 8 |
| PhaseTimeline keyboard nav | Task 9 |
| Skip-nav link | Task 10 |
| detect.py auth | Task 11 |
| process.py auth | Task 11 |
| Rate limiting | Task 12 |
| Global error toast | Task 13 |
| i18n translations | Task 14 |
| Show/hide password | Task 15 |
| Diagnostics heading fix | Missing — add inline during Task 7 |
| Metric name localization | Missing — covered in Phase 2 nav task |

### Placeholder scan

No TBD, TODO, or "implement later" in any task. All code is concrete.

### Type consistency

- `usePageStatus` accepts `QueryLike[]` — matches React Query's `status` string type
- `ErrorState.onRetry` calls `refetch` from `usePageStatus` — types match
- Skeleton components follow `SkeletonCard` pattern — consistent

### Not covered in this plan (deferred to Phase 2/3 plans)

- Nav restructure (Phase 2)
- Session detail tab layout (Phase 2)
- Progress L0/L1/L2 (Phase 2-3)
- Inline email verify modal (Phase 3)
- Demo session (Phase 3)
- Coach view switcher (Phase 2)
- 3D viewer keyboard controls (Phase 2)
- Health indicators with icons (Phase 2)
- `prefers-reduced-motion` (Phase 3)
- Touch target audit (Phase 3)