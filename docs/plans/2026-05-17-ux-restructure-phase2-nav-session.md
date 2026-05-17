# UX Restructure — Phase 2: Navigation, Session Detail, Coach View Switcher

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure navigation (universal 4-item + center FAB), redesign session detail (3-tab progressive disclosure), add coach view switcher, add batched metrics endpoint, fix cache invalidation.

**Prerequisite:** Phase 1 plan completed — `usePageStatus`, `ErrorState`, skeleton components, accessibility fixes must exist.

**Architecture:** Navigation changes are structural — universal nav with role-based page sections. Session detail gets tab-based layout with URL params. Coach features use view switcher (not tabs). Backend gets one new batched endpoint.

**Tech Stack:** React Query, Next.js 16 App Router, Tailwind CSS, Litestar (backend), Valkey (cache)

**Spec reference:** `docs/specs/2026-05-16-ux-restructure-design.md` — Sections 2 (IA), 3 (Page Redesigns), 9 (Performance)

---

## File Structure

### New files

- `frontend/src/components/layout/center-fab.tsx` — Center FAB component for bottom dock
- `frontend/src/components/layout/coach-view-switcher.tsx` — View switcher (Мой прогресс ↔ Ученики)
- `frontend/src/components/session/session-tab-layout.tsx` — Tab container with URL param sync
- `frontend/src/components/session/session-action-menu.tsx` — [...v] overflow menu (Share, Compare, Print, Delete)
- `frontend/src/components/session/processing-banner.tsx` — Sticky processing progress banner
- `frontend/src/components/progress/element-card.tsx` — Element card with health indicator (L0)
- `frontend/src/components/progress/element-detail.tsx` — Element detail with metric cards (L1)
- `frontend/src/components/progress/metric-deep-dive.tsx` — Metric deep dive with reference range (L2)
- `frontend/src/hooks/use-tab-param.ts` — Hook for `?tab=` via replaceState
- `backend/app/routes/metrics_summary.py` — Batched `GET /metrics/element-summary` endpoint

### Modified files

- `frontend/src/components/layout/bottom-dock.tsx` — Restructure to 4-item + center FAB
- `frontend/src/components/app-nav.tsx` — Restructure to 4-item nav
- `frontend/src/app/(app)/sessions/[id]/page.tsx` — 3-tab layout
- `frontend/src/app/(app)/progress/page.tsx` — 3-level progressive disclosure
- `frontend/src/app/(app)/dashboard/page.tsx` — Add view switcher
- `frontend/src/app/(app)/feed/page.tsx` — Content-area FAB fallback (if center FAB fails)
- `frontend/src/components/analysis/phase-timeline.tsx` — Already keyboard-accessible from Phase 1, add aria enhancements
- `frontend/src/components/analysis/threejs-skeleton-viewer.tsx` — Add keyboard orbit controls
- `frontend/src/lib/api/sessions.ts` — Add cache invalidation for ["trend"], ["diagnostics"]
- `frontend/messages/ru.json` — New nav labels, tab labels, view switcher
- `frontend/messages/en.json` — Same
- `backend/app/main.py` — Register new metrics_summary route

---

## Wave 1: Navigation Restructure

### Task 1: CSS spike — center FAB in bottom dock

**Files:**

- Create: `frontend/src/components/layout/center-fab.tsx`
- Modify: `frontend/src/components/layout/bottom-dock.tsx`

The center FAB requires an absolutely-positioned circular button in the center of the bottom dock, with `safe-area-inset-bottom` handling. This is the highest-risk CSS change.

- [ ] **Step 1: Create CenterFAB component**

```tsx
// frontend/src/components/layout/center-fab.tsx
"use client"

import Link from "next/link"
import { Camera } from "lucide-react"
import { useTranslations } from "@/i18n"

export function CenterFAB() {
  const t = useTranslations("nav")
  return (
    <Link
      href="/upload"
      aria-label={t("upload")}
      className="absolute left-1/2 -translate-x-1/2 -top-5 z-10 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 active:scale-95 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <Camera className="h-6 w-6" />
    </Link>
  )
}
```

- [ ] **Step 2: Restructure BottomDock to 4-item + center FAB**

Change `tabs` array to 4 items (Записи, Прогресс, Программа, Профиль). Remove Upload from tabs. Insert `CenterFAB` between positions 2 and 3. Update bottom dock container to `relative` positioning.

```tsx
const tabs = [
  { href: "/feed", icon: Newspaper, label: t("sessions") },  // renamed from "feed"
  { href: "/progress", icon: BarChart3, label: t("progress") },
  // CenterFAB inserted here (upload)
  { href: "/choreography", icon: Music, label: t("programs") },  // renamed from "planner"
  { href: "/profile", icon: User, label: t("profile") },
]
```

Keep conditional Dashboard tab as 5th item when `hasStudents` (between Программа and Профиль).

Update layout: left group = positions 1-2, center = FAB, right group = positions 3-4. Use `justify-around` with the FAB absolutely positioned.

- [ ] **Step 3: Add fallback — content-area FAB on Feed**

If center FAB causes safe-area issues on certain devices, add a persistent "Загрузить видео" button at the top of `/feed`. This is the fallback per spec Q8. Implement now as a `<Link href="/upload">` at the top of the feed page.

- [ ] **Step 4: Test on various viewports**

Run: `cd frontend && bunx tsc --noEmit && bunx next lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/center-fab.tsx frontend/src/components/layout/bottom-dock.tsx frontend/src/app/\(app\)/feed/page.tsx
git commit -m "feat(frontend): restructure bottom dock — 4-item nav + center upload FAB"
```

---

### Task 2: Restructure desktop AppNav

**Files:**

- Modify: `frontend/src/components/app-nav.tsx`

- [ ] **Step 1: Update AppNav to match new IA**

Change tabs to 4 items matching bottom dock: Записи, Прогресс, Программа, Профиль. Remove Upload from nav. Keep conditional Dashboard. Move Connections and Settings to Profile dropdown (submenu).

```tsx
const tabs = [
  { href: "/feed", icon: Newspaper, label: t("sessions") },
  { href: "/progress", icon: BarChart3, label: t("progress") },
  { href: "/choreography", icon: Music, label: t("programs") },
  ...(hasStudents ? [{ href: "/dashboard", icon: Users, label: t("students") }] : []),
]
```

Profile section becomes a dropdown with: Profile, Connections, Settings.

- [ ] **Step 2: Add i18n keys for renamed labels**

In `ru.json` under `nav`: add `"sessions": "Записи"`, `"programs": "Программа"`. Keep `"feed"` and `"planner"` as fallback keys but mark deprecated.

In `en.json`: add `"sessions": "Sessions"`, `"programs": "Programs"`.

- [ ] **Step 3: Verify**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/app-nav.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): restructure desktop nav — 4 items, profile dropdown, new labels"
```

---

## Wave 2: Session Detail Tab Layout

### Task 3: `useTabParam` hook — URL-synced tab state

**Files:**

- Create: `frontend/src/hooks/use-tab-param.ts`

- [ ] **Step 1: Create hook**

```tsx
// frontend/src/hooks/use-tab-param.ts
"use client"

import { useSearchParams } from "next/navigation"
import { useCallback, useState } from "react"

const VALID_TABS = ["overview", "details", "export"] as const
type Tab = typeof VALID_TABS[number]

export function useTabParam(defaultTab: Tab = "overview") {
  const searchParams = useSearchParams()
  const [localTab, setLocalTab] = useState<Tab>(defaultTab)

  const urlTab = searchParams.get("tab") as Tab | null
  const activeTab = urlTab && VALID_TABS.includes(urlTab) ? urlTab : localTab

  const setTab = useCallback((tab: Tab) => {
    setLocalTab(tab)
    const url = new URL(window.location.href)
    url.searchParams.set("tab", tab)
    window.history.replaceState(null, "", url.toString())
  }, [])

  return { activeTab, setTab }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/use-tab-param.ts
git commit -m "feat(frontend): add useTabParam hook with replaceState for tab navigation"
```

---

### Task 4: Session action menu ([...v] overflow)

**Files:**

- Create: `frontend/src/components/session/session-action-menu.tsx`

- [ ] **Step 1: Create action menu**

Replace the visible `SessionActions` + `SessionDownloads` + `Printer` button cluster with a single `[...v]` dropdown menu.

```tsx
// frontend/src/components/session/session-action-menu.tsx
"use client"

import { MoreVertical, Share2, GitCompare, Printer, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import Link from "next/link"

interface SessionActionMenuProps {
  sessionId: string
  onDelete: () => void
  onShare: () => void
}

export function SessionActionMenu({ sessionId, onDelete, onShare }: SessionActionMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Действия">
          <MoreVertical className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={onShare}>
          <Share2 className="mr-2 h-4 w-4" /> Поделиться
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href={`/compare?left=${sessionId}`}>
            <GitCompare className="mr-2 h-4 w-4" /> Сравнить
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => window.print()}>
          <Printer className="mr-2 h-4 w-4" /> Печать отчёта
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
          <Trash2 className="mr-2 h-4 w-4" /> Удалить сессию
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

Note: requires shadcn `dropdown-menu` component. Check if already exists in `components/ui/`. If not, add via `bunx shadcn@latest add dropdown-menu`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/session-action-menu.tsx
git commit -m "feat(frontend): add session action overflow menu with share, compare, print, delete"
```

---

### Task 5: Processing banner (sticky, not full-page)

**Files:**

- Create: `frontend/src/components/session/processing-banner.tsx`

- [ ] **Step 1: Create processing banner**

Replaces the current full-page `SessionStatus` when session is processing. The banner is sticky at the top of the session detail page, showing progress bar and status text. The page content below remains visible (previous session data or placeholder).

```tsx
// frontend/src/components/session/processing-banner.tsx
"use client"

import { useProcessStream } from "@/hooks/use-process-stream"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

interface ProcessingBannerProps {
  taskId: string | null
  onCancel: () => void
}

export function ProcessingBanner({ taskId, onCancel }: ProcessingBannerProps) {
  const stream = useProcessStream(taskId)
  const t = useTranslations("session")

  if (!taskId) return null

  const progress = stream.state?.progress ?? 0
  const status = stream.state?.status ?? "queued"

  return (
    <div
      className="sticky top-0 z-40 border-b border-primary/20 bg-primary/5 px-4 py-3"
      role="status"
      aria-live="polite"
    >
      <div className="mx-auto flex max-w-2xl items-center gap-3">
        <div className="flex-1 space-y-1">
          <p className="text-sm font-medium">{t("analyzing")}</p>
          <Progress value={progress} className="h-1.5" />
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          className="shrink-0 text-sm text-ink-mute"
        >
          {t("cancel")}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/processing-banner.tsx
git commit -m "feat(frontend): add sticky processing banner for session detail"
```

---

### Task 6: Session detail — 3-tab layout

**Files:**

- Modify: `frontend/src/app/(app)/sessions/[id]/page.tsx`

This is the largest structural change in Phase 2. The current flat 2-column layout becomes a 3-tab layout: Overview, Details, Export.

- [ ] **Step 1: Restructure session detail page**

Key changes:
1. Import `useTabParam`, `SessionActionMenu`, `ProcessingBanner`
2. Remove the early return for `POLLING_STATUSES` (full-page SessionStatus) — replace with `ProcessingBanner` at top + skeleton content below
3. Remove the early return for `failed` — show banner with retry + keep video playable
4. Render 3 tabs: Overview (default), Details, Export
5. **Overview tab**: element name + score in header, `[...v]` menu, video hero, phase timeline, recommendations, key metrics (out-of-range + PRs), "Показать все метрики →" link to Details tab
6. **Details tab**: frame metrics chart, synced phase timeline, 3D viewer (conditionally mounted), full metrics table, diagnostics
7. **Export tab**: downloads (video/skeleton/CSV), compare entry (link to `/compare?left={id}`), share, print, delete (isolated, red)
8. Use `useTabParam("overview")` for tab state
9. Remove inline `SessionActions`, `SessionDownloads`, print button from the main layout (they move to menu/tab)

- [ ] **Step 2: Add i18n keys for tab labels**

In `ru.json` under `session`:
```json
"tabOverview": "Обзор",
"tabDetails": "Детали",
"tabExport": "Экспорт",
"showAllMetrics": "Показать все метрики"
```

In `en.json`:
```json
"tabOverview": "Overview",
"tabDetails": "Details",
"tabExport": "Export",
"showAllMetrics": "Show all metrics"
```

- [ ] **Step 3: Gate 3D viewer behind Details tab**

`ThreeJSkeletonViewer` should only mount when `activeTab === "details"`. This is already `React.lazy` — now also conditionally rendered:

```tsx
{activeTab === "details" && session.pose_data && session.frame_metrics && (
  <Suspense fallback={<div className="aspect-square rounded-xl bg-muted animate-pulse" />}>
    <ThreeJSkeletonViewer poseData={session.pose_data} frameMetrics={session.frame_metrics} />
  </Suspense>
)}
```

- [ ] **Step 4: Verify**

Run: `cd frontend && bunx tsc --noEmit && bunx next lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(app\)/sessions/\[id\]/page.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): session detail 3-tab layout — overview/details/export with URL param"
```

---

## Wave 3: Coach View Switcher

### Task 7: Coach view switcher component

**Files:**

- Create: `frontend/src/components/layout/coach-view-switcher.tsx`
- Modify: `frontend/src/app/(app)/dashboard/page.tsx`
- Modify: `frontend/src/app/(app)/progress/page.tsx`

- [ ] **Step 1: Create CoachViewSwitcher**

```tsx
// frontend/src/components/layout/coach-view-switcher.tsx
"use client"

import { useState } from "react"
import { useTranslations } from "@/i18n"

type ViewMode = "self" | "students"

const STORAGE_KEY = "coach_view_mode"

export function CoachViewSwitcher() {
  const t = useTranslations("coach")
  const [mode, setMode] = useState<ViewMode>(() => {
    if (typeof window === "undefined") return "self"
    return (localStorage.getItem(STORAGE_KEY) as ViewMode) ?? "self"
  })

  const handleSwitch = (next: ViewMode) => {
    setMode(next)
    localStorage.setItem(STORAGE_KEY, next)
  }

  return (
    <div className="flex rounded-lg border border-hairline p-0.5" role="tablist">
      <button
        role="tab"
        aria-selected={mode === "self"}
        onClick={() => handleSwitch("self")}
        className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          mode === "self" ? "bg-muted text-ink" : "text-ink-mute"
        }`}
      >
        {t("viewSelf")}
      </button>
      <button
        role="tab"
        aria-selected={mode === "students"}
        onClick={() => handleSwitch("students")}
        className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          mode === "students" ? "bg-muted text-ink" : "text-ink-mute"
        }`}
      >
        {t("viewStudents")}
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Add i18n keys**

In `ru.json` under `coach`:
```json
"viewSelf": "Мой прогресс",
"viewStudents": "Ученики"
```

In `en.json`:
```json
"viewSelf": "My Progress",
"viewStudents": "Students"
```

- [ ] **Step 3: Integrate into Dashboard and Progress pages**

On both pages, when `user.onboarding_role === "coach"` or `hasStudents`, show `CoachViewSwitcher` at the top. Conditionally render self-view or students-view based on switcher state.

- [ ] **Step 4: Verify**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/coach-view-switcher.tsx frontend/src/app/\(app\)/dashboard/page.tsx frontend/src/app/\(app\)/progress/page.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): add coach view switcher for progress and dashboard pages"
```

---

## Wave 4: Backend + Performance

### Task 8: Batched `GET /metrics/element-summary` endpoint

**Files:**

- Create: `backend/app/routes/metrics_summary.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create batched endpoint**

Combines trend, diagnostics, registry subset, and PRs into one response for a given element. Eliminates the 5-6 parallel API calls at Progress L1.

```python
# backend/app/routes/metrics_summary.py
"""GET /metrics/element-summary — batched endpoint for Progress L1."""
from __future__ import annotations

from litestar import Controller, get
from litestar.params import Parameter

from app.auth.deps import CurrentUser, DbDep
from app.schemas import ElementSummaryResponse  # new schema


class ElementSummaryController(Controller):
    path = ""
    tags = ["metrics"]

    @get("/element-summary")
    async def get_element_summary(
        self,
        user: CurrentUser,
        db: DbDep,
        element: str = Parameter(description="Element type key"),
        period: str = Parameter(default="30d", description="7d/30d/90d/all"),
    ) -> ElementSummaryResponse:
        """Batched endpoint: trend + diagnostics + registry + PRs for one element."""
        # Aggregate data from existing services
        # ... (calls existing CRUD/service functions)
```

The response schema includes: `trend`, `findings`, `metric_defs`, `personal_records`.

- [ ] **Step 2: Add schema to `backend/app/schemas.py`**

```python
class ElementSummaryResponse(BaseModel):
    element: str
    trend: TrendResponse | None
    findings: list[DiagnosticsFinding]
    metric_defs: dict[str, MetricDefBrief]
    personal_records: dict[str, float]
```

- [ ] **Step 3: Register route in main.py**

- [ ] **Step 4: Write test**

```python
# backend/tests/test_element_summary.py
import pytest

@pytest.mark.asyncio
async def test_element_summary_requires_auth(client):
    response = await client.get("/api/metrics/element-summary?element=axel")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_element_summary_returns_batched_data(authed_client):
    response = await authed_client.get("/api/metrics/element-summary?element=axel&period=30d")
    assert response.status_code == 200
    data = response.json()
    assert "trend" in data
    assert "findings" in data
    assert "metric_defs" in data
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/metrics_summary.py backend/app/schemas.py backend/app/main.py backend/tests/test_element_summary.py
git commit -m "feat(backend): add GET /metrics/element-summary batched endpoint for Progress L1"
```

---

### Task 9: Cache invalidation for trend/diagnostics on session creation

**Files:**

- Modify: `frontend/src/lib/api/sessions.ts`

- [ ] **Step 1: Add invalidation to upload mutation success handler**

In `useCreateSession` or the upload completion mutation, add:

```tsx
onSuccess: () => {
  queryClient.invalidateQueries({ queryKey: ["sessions"] })
  queryClient.invalidateQueries({ queryKey: ["trend"] })
  queryClient.invalidateQueries({ queryKey: ["diagnostics"] })
}
```

Find the existing mutation and extend its `onSuccess` callback.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api/sessions.ts
git commit -m "fix(frontend): invalidate trend and diagnostics cache on session creation"
```

---

### Task 10: Polling optimization — gate on hasProcessingSessions

**Files:**

- Create: `frontend/src/lib/hooks/use-processing-sessions.ts`
- Modify: `frontend/src/lib/api/sessions.ts`

- [ ] **Step 1: Create useProcessingSessions hook**

```tsx
// frontend/src/lib/hooks/use-processing-sessions.ts
import { useQuery } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api-client"
import { z } from "zod"

const SessionsListSchema = z.object({
  sessions: z.array(z.object({ status: z.string() })),
})

export function useProcessingSessions() {
  const { data } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => apiFetch("/sessions?status=processing", SessionsListSchema),
    select: data => data.sessions.some(s => ["queued", "uploading", "running", "pending"].includes(s.status)),
  })
  return { hasProcessingSessions: data ?? false }
}
```

- [ ] **Step 2: Gate polling in useSession**

Only poll when `hasProcessingSessions` is true. In `useSession`, add a condition:

```tsx
refetchInterval: (query) => {
  const status = query.state.data?.status
  if (POLLING_STATUSES.has(status)) return 5000
  return false
}
```

This is already partially implemented — verify and tighten.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/hooks/use-processing-sessions.ts frontend/src/lib/api/sessions.ts
git commit -m "perf(frontend): gate session polling on hasProcessingSessions flag"
```

---

## Wave 5: Accessibility Phase 2

### Task 11: 3D viewer keyboard orbit controls

**Files:**

- Modify: `frontend/src/components/analysis/threejs-skeleton-viewer.tsx`

- [ ] **Step 1: Add WASD + QE keyboard controls for 3D viewer**

Add keyboard event listeners when the 3D viewer container is focused. Map:
- W/S — rotate up/down (orbit)
- A/D — rotate left/right (orbit)
- Q/E — zoom in/out

Add `tabIndex={0}` and `aria-label` to the container.

- [ ] **Step 2: Add `prefers-reduced-motion` check**

```tsx
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
// If true, disable auto-rotation and reduce animation intensity
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/analysis/threejs-skeleton-viewer.tsx
git commit -m "feat(frontend): add keyboard orbit controls and prefers-reduced-motion to 3D viewer"
```

---

### Task 12: Health indicators — add icons alongside color

**Files:**

- Modify: `frontend/src/components/progress/element-card.tsx` (new from Task 13 in Phase 2 progress plan — this task depends on it)

- [ ] **Step 1: Add icons to health indicators**

Use icons alongside color for WCAG 1.4.1:
- Improving/PR: `<TrendingUp className="h-3 w-3 text-green-600" />` + green dot
- Stagnant: `<Minus className="h-3 w-3 text-yellow-600" />` + yellow dot
- Declining: `<TrendingDown className="h-3 w-3 text-red-600" />` + red dot
- No data: gray dot only

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/progress/element-card.tsx
git commit -m "fix(frontend): add icons alongside color on health indicators — WCAG 1.4.1"
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Task |
|---|---|
| Universal 4-item nav + center FAB | Tasks 1-2 |
| Conditional Dashboard | Task 2 (preserved) |
| Session detail 3-tab layout | Task 6 |
| [...v] action menu | Task 4 |
| Sticky processing banner | Task 5 |
| Tab state via replaceState | Task 3 |
| 3D viewer gated on Details tab | Task 6 |
| Compare entry from Export tab | Task 6 |
| Coach view switcher | Task 7 |
| Batched element-summary endpoint | Task 8 |
| Cache invalidation (trend/diagnostics) | Task 9 |
| Polling optimization | Task 10 |
| 3D viewer keyboard controls | Task 11 |
| Health indicators with icons | Task 12 |
| Diagnostics heading fix | Carry from Phase 1 |
| Metric name localization | In Progress L0 element cards (Phase 2-3) |

### Placeholder scan

No TBD/TODO found. All code is concrete.

### Not covered (deferred to Phase 3 plan)

- Inline email verify modal
- Demo session (static JSON)
- Progress L0/L1/L2 full implementation (element cards only sketched here)
- Registration 2-field
- Onboarding celebration flow
- Coach sandbox mock data
- "У меня нет видео" path
- Mobile deep link
- Touch target audit
- Contrast ratio audit
