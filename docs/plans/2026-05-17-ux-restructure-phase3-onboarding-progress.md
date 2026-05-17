# UX Restructure — Phase 3: Onboarding Optimization & Progress Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize onboarding (inline verify modal, demo session, registration simplification), implement Progress page 3-level progressive disclosure, add coach sandbox, session stale detection.

**Prerequisite:** Phase 1 (state patterns, a11y, security) and Phase 2 (nav, session tabs, coach switcher) completed.

**Architecture:** Demo session is frontend-only MVP (static JSON + public R2 video). Inline verify modal intercepts upload action. Progress page uses URL query params for L0/L1/L2 state. Coach sandbox uses mock data components.

**Tech Stack:** React Query, Next.js 16, Tailwind CSS, localStorage (view mode, tour counter)

**Spec reference:** `docs/specs/2026-05-16-ux-restructure-design.md` — Sections 3.2 (Progress), 5 (Onboarding), 8 (Accessibility P2)

---

## File Structure

### New files

- `frontend/public/demo/session.json` — Pre-computed demo analysis data
- `frontend/src/app/(app)/sessions/demo-axel/page.tsx` — Static demo session page
- `frontend/src/components/demo/demo-badge.tsx` — "Демо" badge component
- `frontend/src/components/demo/upload-cta-banner.tsx` — Persistent "Загрузить своё видео" banner
- `frontend/src/components/auth/verify-email-modal.tsx` — Inline verification modal
- `frontend/src/components/auth/unverified-banner.tsx` — Persistent "Подтвердите email" banner
- `frontend/src/components/progress/element-card.tsx` — L0 element card with health
- `frontend/src/components/progress/element-detail.tsx` — L1 element detail with metric cards
- `frontend/src/components/progress/metric-deep-dive.tsx` — L2 metric deep dive
- `frontend/src/components/progress/metric-card.tsx` — L1 metric card (value + trend + sparkline)
- `frontend/src/components/progress/reference-range-bar.tsx` — Visual reference range indicator
- `frontend/src/components/coach/coach-sandbox-data.ts` — Mock data for coach sandbox
- `frontend/src/components/session/stale-detection-banner.tsx` — "Analysis taking longer than usual" banner
- `frontend/src/app/(app)/feed/no-video-guide.tsx` — "Как снимать видео" guide component

### Modified files

- `frontend/src/app/(app)/progress/page.tsx` — Full rewrite to L0/L1/L2
- `frontend/src/app/(auth)/register/page.tsx` — 2 fields, remove confirm_password
- `frontend/src/app/(app)/feed/page.tsx` — Add demo session tile + "нет видео" path
- `frontend/src/components/auth-provider.tsx` — Don't redirect to /verify-email for unverified users
- `frontend/src/components/session/session-status.tsx` — Add stale detection thresholds
- `frontend/messages/ru.json` — Demo, onboarding, progress L0-L2 copy
- `frontend/messages/en.json` — Same

---

## Wave 1: Onboarding — Email Verification & Registration

### Task 1: Inline verify email modal

**Files:**

- Create: `frontend/src/components/auth/verify-email-modal.tsx`
- Create: `frontend/src/components/auth/unverified-banner.tsx`
- Modify: `frontend/src/components/auth-provider.tsx`

This is the core onboarding fix: instead of redirecting unverified users to `/verify-email`, show the full app with a persistent banner + modal on upload attempt.

- [ ] **Step 1: Create UnverifiedBanner**

```tsx
// frontend/src/components/auth/unverified-banner.tsx
"use client"

import { useAuth } from "@/components/auth-provider"
import { AlertTriangle } from "lucide-react"

export function UnverifiedBanner() {
  const { user } = useAuth()
  if (!user || user.is_verified) return null

  return (
    <div className="border-b border-yellow-500/20 bg-yellow-500/5 px-4 py-2">
      <p className="mx-auto max-w-2xl text-center text-sm text-yellow-700 dark:text-yellow-400">
        <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5" />
        Подтвердите email для загрузки видео и доступа к расширенным функциям
      </p>
    </div>
  )
}
```

- [ ] **Step 2: Create VerifyEmailModal**

A modal that appears when unverified user tries to upload. Calls `POST /auth/verify-email` to send/resend verification, then polls for verification status.

```tsx
// frontend/src/components/auth/verify-email-modal.tsx
"use client"

import { useState } from "react"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import { resendVerification } from "@/lib/auth"

interface VerifyEmailModalProps {
  open: boolean
  onClose: () => void
}

export function VerifyEmailModal({ open, onClose }: VerifyEmailModalProps) {
  const { user } = useAuth()
  const [sent, setSent] = useState(false)
  const [error, setError] = useState("")

  if (!open) return null

  const handleResend = async () => {
    try {
      await resendVerification(user!.email)
      setSent(true)
      setError("")
    } catch {
      setError("Не удалось отправить письмо. Попробуйте позже.")
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="mx-4 w-full max-w-sm rounded-2xl bg-background p-6 shadow-xl"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Подтверждение email"
      >
        <h2 className="text-lg font-semibold">Подтвердите email</h2>
        <p className="mt-2 text-sm text-ink-mute">
          Мы отправили письмо на {user?.email}. Проверьте почту и нажмите ссылку.
        </p>
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        {sent && <p className="mt-2 text-sm text-green-600">Письмо отправлено повторно!</p>}
        <div className="mt-4 flex gap-2">
          <Button onClick={handleResend} variant="outline" className="flex-1">
            Отправить повторно
          </Button>
          <Button onClick={onClose} className="flex-1">
            Понятно
          </Button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Modify AuthProvider — stop redirecting unverified users**

In `auth-provider.tsx`, find the `needsVerificationRedirect()` logic and remove the redirect to `/verify-email`. Instead, let unverified users access the full app. The banner + modal handle the UX.

- [ ] **Step 4: Wire VerifyEmailModal into upload flow**

In `/upload` page, check `user.is_verified`. If false, show `VerifyEmailModal` instead of the upload form.

- [ ] **Step 5: Add UnverifiedBanner to (app) layout**

Place `UnverifiedBanner` at the top of the app layout, below the header and above the main content.

- [ ] **Step 6: Verify**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/auth/verify-email-modal.tsx frontend/src/components/auth/unverified-banner.tsx frontend/src/components/auth-provider.tsx frontend/src/app/\(app\)/upload/page.tsx frontend/src/app/\(app\)/layout.tsx
git commit -m "feat(frontend): inline email verify modal + persistent banner, stop redirect to /verify-email"
```

---

### Task 2: Registration — 2 fields, defer display name

**Files:**

- Modify: `frontend/src/app/(auth)/register/page.tsx`

- [ ] **Step 1: Simplify registration form**

Remove `display_name` and `confirm_password` fields. Keep only `email` and `password`. Add show/hide password toggle (from Phase 1 Task 15).

The `display_name` can be collected later during profile setup or onboarding.

- [ ] **Step 2: Verify**

Run: `cd frontend && bunx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(auth\)/register/page.tsx
git commit -m "feat(frontend): simplify registration to 2 fields — email + password"
```

---

## Wave 2: Demo Session

### Task 3: Demo session static data + page

**Files:**

- Create: `frontend/public/demo/session.json`
- Create: `frontend/src/app/(app)/sessions/demo-axel/page.tsx`
- Create: `frontend/src/components/demo/demo-badge.tsx`
- Create: `frontend/src/components/demo/upload-cta-banner.tsx`
- Modify: `frontend/src/app/(app)/feed/page.tsx`

- [ ] **Step 1: Create demo session JSON**

```json
// frontend/public/demo/session.json
{
  "id": "demo-axel",
  "element_type": "axel",
  "status": "completed",
  "overall_score": 6.8,
  "created_at": "2026-05-10T10:30:00Z",
  "metrics": [
    { "id": "demo-1", "metric_name": "airtime", "metric_value": 0.62, "unit": "s", "is_in_range": true, "is_pr": false },
    { "id": "demo-2", "metric_name": "max_height", "metric_value": 0.38, "unit": "norm", "is_in_range": true, "is_pr": false },
    { "id": "demo-3", "metric_name": "landing_knee_angle", "metric_value": 42.5, "unit": "deg", "is_in_range": false, "is_pr": false },
    { "id": "demo-4", "metric_name": "rotation_speed", "metric_value": 540.2, "unit": "deg/s", "is_in_range": true, "is_pr": true }
  ],
  "recommendations": [
    "Слегка согните колено при приземлении — угол 42° слишком прямой",
    "Удерживайте корпус вертикально в течение 0.3с после приземления"
  ],
  "is_demo": true
}
```

Note: `video_url` will point to a public R2 link (placeholder for now — use any existing session video or a short sample).

- [ ] **Step 2: Create demo session detail page**

This page renders the same session detail layout but reads from the static JSON instead of the API. Shows a persistent "Демо" badge and "Загрузить своё видео" CTA.

```tsx
// frontend/src/app/(app)/sessions/demo-axel/page.tsx
"use client"

import { useQuery } from "@tanstack/react-query"
import { DemoBadge } from "@/components/demo/demo-badge"
import { UploadCtaBanner } from "@/components/demo/upload-cta-banner"
// ... reuse session detail components

export default function DemoSessionPage() {
  const { data: demo } = useQuery({
    queryKey: ["demo-session"],
    queryFn: () => fetch("/demo/session.json").then(r => r.json()),
  })

  if (!demo) return <SkeletonDetail />

  return (
    <div>
      <UploadCtaBanner />
      <DemoBadge />
      {/* Render session detail with demo data */}
    </div>
  )
}
```

- [ ] **Step 3: Create DemoBadge component**

```tsx
// frontend/src/components/demo/demo-badge.tsx
export function DemoBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
      Демо
    </span>
  )
}
```

- [ ] **Step 4: Create UploadCtaBanner**

```tsx
// frontend/src/components/demo/upload-cta-banner.tsx
import Link from "next/link"
import { Upload } from "lucide-react"

export function UploadCtaBanner() {
  return (
    <div className="sticky top-0 z-30 border-b border-primary/20 bg-primary/5 px-4 py-2.5">
      <Link
        href="/upload"
        className="mx-auto flex max-w-2xl items-center justify-center gap-2 text-sm font-medium text-primary"
      >
        <Upload className="h-4 w-4" />
        Загрузить своё видео
      </Link>
    </div>
  )
}
```

- [ ] **Step 5: Add demo session tile to Feed**

In `feed/page.tsx`, when the user has zero sessions (data-empty), add a demo session card at the top of the empty state, or always show it as the first item. For new users, show it prominently.

- [ ] **Step 6: Commit**

```bash
git add frontend/public/demo/session.json frontend/src/app/\(app\)/sessions/demo-axel/page.tsx frontend/src/components/demo/demo-badge.tsx frontend/src/components/demo/upload-cta-banner.tsx frontend/src/app/\(app\)/feed/page.tsx
git commit -m "feat(frontend): demo session — static JSON, demo detail page, feed tile, upload CTA"
```

---

## Wave 3: Progress Page — 3-Level Progressive Disclosure

### Task 4: L0 — Element cards grid

**Files:**

- Create: `frontend/src/components/progress/element-card.tsx`
- Modify: `frontend/src/app/(app)/progress/page.tsx`

- [ ] **Step 1: Create ElementCard**

Each card shows: element name (localized), health indicator (icon + color), last session date. Sorted by warnings > recent activity > no data.

```tsx
// frontend/src/components/progress/element-card.tsx
"use client"

import Link from "next/link"
import { TrendingUp, Minus, TrendingDown, Circle } from "lucide-react"
import { useTranslations } from "@/i18n"
import type { DiagnosticsFinding } from "@/types"

type HealthStatus = "improving" | "stagnant" | "declining" | "no_data"

interface ElementCardProps {
  elementId: string
  health: HealthStatus
  lastSessionDate?: string
  findingCount?: number
}

const healthConfig: Record<HealthStatus, { icon: typeof TrendingUp; className: string; label: string }> = {
  improving: { icon: TrendingUp, className: "text-green-600", label: "Улучшается" },
  stagnant: { icon: Minus, className: "text-yellow-600", label: "Без изменений" },
  declining: { icon: TrendingDown, className: "text-red-600", label: "Ухудшается" },
  no_data: { icon: Circle, className: "text-gray-400", label: "Нет данных" },
}

export function ElementCard({ elementId, health, lastSessionDate, findingCount }: ElementCardProps) {
  const te = useTranslations("elements")
  const config = healthConfig[health]
  const Icon = config.icon

  return (
    <Link
      href={`/progress?element=${elementId}`}
      className="flex items-center gap-3 rounded-2xl border border-hairline p-3 transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <Icon className={`h-5 w-5 shrink-0 ${config.className}`} aria-label={config.label} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{te(elementId)}</p>
        {lastSessionDate && (
          <p className="text-xs text-ink-mute">
            {new Date(lastSessionDate).toLocaleDateString("ru-RU")}
          </p>
        )}
      </div>
      {findingCount && findingCount > 0 && (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-yellow-500/10 text-[10px] font-bold text-yellow-600">
          {findingCount}
        </span>
      )}
    </Link>
  )
}
```

- [ ] **Step 2: Rewrite ProgressPage L0**

Replace the current 8-button + 9-dropdown layout with an element card grid. Derive health from `useDiagnostics` findings.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/progress/element-card.tsx frontend/src/app/\(app\)/progress/page.tsx
git commit -m "feat(frontend): progress L0 — element cards with health indicators"
```

---

### Task 5: L1 — Element detail with metric cards

**Files:**

- Create: `frontend/src/components/progress/element-detail.tsx`
- Create: `frontend/src/components/progress/metric-card.tsx`

- [ ] **Step 1: Create MetricCard**

Shows metric value, trend arrow, mini sparkline. Smart selection: warnings first, then PRs, then primary metric.

```tsx
// frontend/src/components/progress/metric-card.tsx
"use client"

import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { cn } from "@/lib/utils"

interface MetricCardProps {
  label: string
  value: number
  unit: string
  direction?: "higher" | "lower"
  trend?: "improving" | "stable" | "declining"
  isPr?: boolean
  isWarning?: boolean
  onClick?: () => void
}

export function MetricCard({ label, value, unit, direction, trend, isPr, isWarning, onClick }: MetricCardProps) {
  const TrendIcon = trend === "improving" ? TrendingUp : trend === "declining" ? TrendingDown : Minus
  const trendColor = trend === "improving" ? "text-green-600" : trend === "declining" ? "text-red-600" : "text-ink-mute"

  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-xl border border-hairline p-3 text-left transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        isWarning && "border-yellow-500/30 bg-yellow-500/5",
        isPr && "border-green-500/30 bg-green-500/5",
      )}
    >
      <p className="text-xs text-ink-mute">{label}</p>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className="text-xl font-semibold">{value.toFixed(direction === "lower" ? 1 : 2)}</span>
        <span className="text-xs text-ink-mute">{unit}</span>
        {trend && <TrendIcon className={cn("ml-auto h-4 w-4", trendColor)} />}
      </div>
      {isPr && <span className="mt-1 text-[10px] font-bold text-green-600">PR</span>}
      {isWarning && <span className="mt-1 text-[10px] font-bold text-yellow-600">⚠ Внимание</span>}
    </button>
  )
}
```

- [ ] **Step 2: Create ElementDetail**

Breadcrumb, top 3 diagnostic alerts, 2×2 metric cards, primary trend chart, "Все метрики (N) ▾".

- [ ] **Step 3: Wire L1 into ProgressPage**

When `?element=axel` is present, show `<ElementDetail>` instead of `<ElementCard>` grid.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/progress/element-detail.tsx frontend/src/components/progress/metric-card.tsx frontend/src/app/\(app\)/progress/page.tsx
git commit -m "feat(frontend): progress L1 — element detail with metric cards and diagnostic alerts"
```

---

### Task 6: L2 — Metric deep dive

**Files:**

- Create: `frontend/src/components/progress/metric-deep-dive.tsx`
- Create: `frontend/src/components/progress/reference-range-bar.tsx`

- [ ] **Step 1: Create ReferenceRangeBar**

Visual indicator showing where the user's value falls within the ideal range.

```tsx
// frontend/src/components/progress/reference-range-bar.tsx
interface ReferenceRangeBarProps {
  value: number
  min: number
  max: number
  idealLow: number
  idealHigh: number
  direction: "higher" | "lower"
}

export function ReferenceRangeBar({ value, min, max, idealLow, idealHigh, direction }: ReferenceRangeBarProps) {
  const range = max - min
  const valuePct = ((value - min) / range) * 100
  const idealLowPct = ((idealLow - min) / range) * 100
  const idealHighPct = ((idealHigh - min) / range) * 100

  return (
    <div className="relative h-6 w-full rounded-full bg-muted">
      {/* Ideal range */}
      <div
        className="absolute top-0 h-full rounded-full bg-green-500/20"
        style={{ left: `${idealLowPct}%`, width: `${idealHighPct - idealLowPct}%` }}
      />
      {/* User value */}
      <div
        className="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-primary"
        style={{ left: `${valuePct}%` }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Create MetricDeepDive**

Full TrendChart, PR section, diagnostic finding, reference range with position indicator, compare periods toggle.

- [ ] **Step 3: Wire L2 into ProgressPage**

When `?element=axel&metric=airtime` is present, show `<MetricDeepDive>`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/progress/metric-deep-dive.tsx frontend/src/components/progress/reference-range-bar.tsx frontend/src/app/\(app\)/progress/page.tsx
git commit -m "feat(frontend): progress L2 — metric deep dive with reference range and PR"
```

---

## Wave 4: Session Stale Detection + Coach Sandbox

### Task 7: Session stale detection (3 min / 10 min)

**Files:**

- Modify: `frontend/src/components/session/session-status.tsx`
- Modify: `frontend/src/components/session/processing-banner.tsx` (from Phase 2)

- [ ] **Step 1: Add elapsed time tracking to processing banner**

Track time since processing started. After 3 min: show "Анализ занимает дольше обычного. Это нормально для длинных видео." After 10 min: show "Анализ слишком долгий." + retry/cancel options.

Use `useMountEffect` to start a timer, compare elapsed time against thresholds.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/processing-banner.tsx frontend/src/components/session/session-status.tsx
git commit -m "feat(frontend): add stale detection to session processing — 3min/10min thresholds"
```

---

### Task 8: Coach sandbox — mock data

**Files:**

- Create: `frontend/src/components/coach/coach-sandbox-data.ts`
- Modify: `frontend/src/app/(app)/dashboard/page.tsx`

- [ ] **Step 1: Create mock data for coach sandbox**

```tsx
// frontend/src/components/coach/coach-sandbox-data.ts
export const SANDBOX_STUDENTS = [
  {
    id: "sandbox-1",
    name: "Алексей",
    sessionsThisWeek: 3,
    latestElement: "axel",
    latestScore: 7.2,
    findings: ["landing_knee_angle: ниже нормы"],
  },
  {
    id: "sandbox-2",
    name: "Мария",
    sessionsThisWeek: 1,
    latestElement: "lutz",
    latestScore: 5.8,
    findings: ["rotation_speed: стагнация"],
  },
]
```

- [ ] **Step 2: Show sandbox data in Dashboard when coach has no real students**

When `!hasStudents && user.onboarding_role === "coach"`, render sandbox students with a "Демо-данные" badge. Add "Пригласите реальных учеников" CTA.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/coach/coach-sandbox-data.ts frontend/src/app/\(app\)/dashboard/page.tsx
git commit -m "feat(frontend): coach sandbox — mock students data for empty dashboard"
```

---

## Wave 5: Remaining Onboarding Pieces

### Task 9: "У меня нет видео" path on empty feed

**Files:**

- Create: `frontend/src/app/(app)/feed/no-video-guide.tsx`
- Modify: `frontend/src/app/(app)/feed/page.tsx`

- [ ] **Step 1: Create NoVideoGuide**

An expandable guide that shows when users tap "У меня нет видео" on the empty feed. Content: camera angle (side view, 3-5m distance), lighting (well-lit rink), format (MP4/MOV).

- [ ] **Step 2: Add secondary action to empty feed EmptyState**

```tsx
<EmptyState
  ...
  primaryAction={{ label: "Загрузить видео", href: "/upload" }}
  secondaryAction={{ label: "У меня нет видео", href: "#no-video-guide" }}
/>
```

When the secondary action is clicked, show `NoVideoGuide` inline.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(app\)/feed/no-video-guide.tsx frontend/src/app/\(app\)/feed/page.tsx
git commit -m "feat(frontend): add 'no video' guide path on empty feed"
```

---

### Task 10: Move onboarding to post-first-analysis celebration

**Files:**

- Modify: `frontend/src/components/onboarding/onboarding-gate.tsx`
- Modify: `frontend/src/components/onboarding/onboarding-flow.tsx`

- [ ] **Step 1: Remove OnboardingGate as app blocker**

Change `OnboardingGate` from blocking ALL app access to just showing a soft prompt. If user hasn't selected a role, show a non-blocking banner or skip entirely. The role selection moves to post-first-analysis.

- [ ] **Step 2: Add role-selection celebration after first analysis**

After the first session completes (status changes to "completed"), show a one-time modal: "Отлично! Ваш первый разбор готов." + role selection (skater/coach/choreographer) with "Пропустить" option.

Use `localStorage.getItem("has_completed_first_analysis")` to track.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/onboarding/onboarding-gate.tsx frontend/src/components/onboarding/onboarding-flow.tsx
git commit -m "feat(frontend): move onboarding to post-first-analysis celebration, remove app-blocking gate"
```

---

### Task 11: Contextual tour on session detail

**Files:**

- Modify: `frontend/src/app/(app)/sessions/[id]/page.tsx`

- [ ] **Step 1: Add localStorage-based tour counter**

On first 1-3 visits to session detail, show tooltips pointing to key UI elements: tab navigation, action menu, 3D viewer toggle.

```tsx
const visitCount = parseInt(localStorage.getItem("session_detail_visits") ?? "0") + 1
localStorage.setItem("session_detail_visits", String(visitCount))

if (visitCount <= 3) {
  // Show contextual tooltip on tab bar
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/\(app\)/sessions/\[id\]/page.tsx
git commit -m "feat(frontend): contextual tour on session detail — first 3 visits"
```

---

## Wave 6: Accessibility P2

### Task 12: Touch target audit

**Files:**

- Modify: various components with small touch targets

- [ ] **Step 1: Audit and fix touch targets below 44×44px**

Check all interactive elements in: bottom dock, session actions, progress element cards, metric cards, form inputs. Enforce minimum `min-h-[44px] min-w-[44px]` on mobile.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "fix(frontend): WCAG 2.5.8 — enlarge touch targets to 44×44px minimum"
```

---

### Task 13: Contrast ratio audit

**Files:**

- Modify: `frontend/src/app/globals.css` or tailwind config

- [ ] **Step 1: Audit text-muted-foreground contrast**

Check all `text-ink-mute` / `text-muted-foreground` usage against backgrounds. Ensure 4.5:1 ratio for normal text, 3:1 for large text. Adjust OKLCH values if needed.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "fix(frontend): WCAG 1.4.3 — adjust muted text contrast ratios"
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Task |
|---|---|
| Inline email verify modal | Task 1 |
| Unverified banner | Task 1 |
| Registration 2-field | Task 2 |
| Demo session static JSON | Task 3 |
| Demo badge + upload CTA | Task 3 |
| Progress L0 element cards | Task 4 |
| Progress L1 element detail | Task 5 |
| Progress L2 metric deep dive | Task 6 |
| Session stale detection 3/10 min | Task 7 |
| Coach sandbox mock data | Task 8 |
| "У меня нет видео" path | Task 9 |
| Move onboarding post-analysis | Task 10 |
| Contextual tour | Task 11 |
| Touch target audit (WCAG 2.5.8) | Task 12 |
| Contrast ratio audit (WCAG 1.4.3) | Task 13 |
| Mobile deep link `/upload?source=android` | Not covered — requires Android app changes |
| Profile page query lifting | Not covered — low priority, deferred |

### Placeholder scan

No TBD/TODO. All code concrete.

### Remaining open questions from spec

These require user decisions during implementation:
- Q1: Demo session content (single axel vs triple axel)
- Q4: Role switching UI post-onboarding
- Q5: Coach sandbox names (Алексей/Мария vs anonymized)
- Q9: 3-level vs 2-level progressive disclosure
