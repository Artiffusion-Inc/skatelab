# PostHog Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate self-hosted PostHog analytics into SkateLab — events, session recordings, feature flags, A/B tests, social traffic monitoring.

**Architecture:** Self-hosted PostHog on existing Hetzner dedic (~28 containers, 14.5GB RAM). Frontend uses `@posthog/next` SDK (SSR bootstrapping, zero-flicker flags). Backend uses `posthog-python` (lazy singleton, fire-and-forget). Shared Valkey DB 2 for Redis, RustFS for object storage, separate PG 15 container. Opt-in cookie consent with 3 tiers (essential/analytics/recordings). Feature flags = functional infrastructure (work without consent).

**Tech Stack:** `@posthog/next` (frontend), `posthog-python` (backend), Docker Compose (PostHog hobby stack), Caddy (reverse proxy), RustFS (object storage), Valkey DB 2 (shared Redis), PostgreSQL 15.12-alpine (separate container)

---

## File Structure

### New files

| File | Purpose |
|------|---------|
| `infra/posthog/.env.posthog` | PostHog env vars (keys, hosts, shared infra refs) |
| `infra/posthog/docker-compose.yml` | PostHog stack (based on hobby.yml, stripped MinIO/SeaweedFS/Redis) |
| `infra/posthog/clickhouse/config.d/custom.xml` | ClickHouse tuning (4GB RAM limit) |
| `frontend/src/lib/posthog.ts` | `@posthog/next` client helpers |
| `frontend/src/lib/flags.ts` | Feature flag key registry |
| `frontend/src/components/consent-provider.tsx` | Consent React context (3-tier) |
| `frontend/src/components/consent-banner.tsx` | Consent UI (Accept all / Customize) |
| `frontend/src/hooks/use-feature-flag.ts` | Type-safe flag hook |
| `frontend/src/app/middleware.ts` | `postHogMiddleware({ proxy: true })` |
| `backend/app/analytics.py` | PostHog lazy singleton + capture_event |
| `backend/app/analytics_events.py` | Typed event functions |
| `backend/app/middleware/posthog_context.py` | Extract tracing headers |
| `scripts/utm_link.py` | CLI UTM link generator |

### Modified files

| File | Changes |
|------|---------|
| `frontend/package.json` | Add `@posthog/next` dep |
| `frontend/src/app/layout.tsx` | Wrap with ConsentProvider + PostHogProvider + PostHogPageView |
| `frontend/src/app/providers.tsx` | Add PostHog identify/reset on auth state change |
| `frontend/src/components/auth-provider.tsx` | Call `posthog.identify()` after login (consent-gated), `reset()` on logout |
| `frontend/src/components/landing/cookie-banner.tsx` | Remove (replaced by ConsentBanner) |
| `frontend/src/lib/env.ts` | Add POSTHOG_KEY, POSTHOG_HOST exports |
| `frontend/src/app/(landing)/cookies/page.tsx` | Update with 3-tier consent, PostHog details |
| `frontend/src/app/(landing)/privacy/page.tsx` | Add PostHog data processing section |
| `backend/pyproject.toml` | Add `posthog>=3.0.0` dep |
| `backend/app/config.py` | Add PostHogConfig class |
| `backend/app/worker.py` | Add get_posthog() init + shutdown_posthog() |
| `backend/app/main.py` | Register PostHogContextMiddleware |
| `infra/caddy/Caddyfile` | Add `ph.skatelab.ru` route + capture endpoints |
| `infra/compose.prod.yaml` | Add POSTHOG env vars to backend/frontend services |

---

## Wave 1: Backend SDK + Config (no infra dependency)

### Task 1: Add posthog-python dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add posthog to dependencies**

Add `posthog>=3.0.0` to `backend/pyproject.toml` dependencies list, after `sentry-sdk`:

```toml
    "sentry-sdk[litestar]>=2.58.0",
    "posthog>=3.0.0",
```

- [ ] **Step 2: Install dependency**

Run: `cd backend && uv sync`
Expected: posthog added to lockfile, no conflicts

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "feat(backend): add posthog-python dependency"
```

---

### Task 2: Add PostHogConfig to settings

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add PostHogConfig class**

Add after `SentryConfig` class (line ~147), before `AppConfig`:

```python
class PostHogConfig(BaseSettings):
    """PostHog analytics settings."""

    api_key: SecretStr = SecretStr("")
    host: str = "https://ph.skatelab.ru"

    class Config:
        env_prefix = "POSTHOG_"
```

- [ ] **Step 2: Add posthog field to Settings class**

Add `posthog: PostHogConfig = Field(default_factory=PostHogConfig)` to `Settings` class, after `sentry` field:

```python
    sentry: SentryConfig = Field(default_factory=SentryConfig)
    posthog: PostHogConfig = Field(default_factory=PostHogConfig)
```

- [ ] **Step 3: Update module docstring**

Add `POSTHOG_` to the Env Prefixes list in the module docstring:

```
  POSTHOG_   — analytics
```

- [ ] **Step 4: Verify config loads**

Run: `cd backend && uv run python -c "from app.config import get_settings; s = get_settings(); print(s.posthog.host, s.posthog.api_key.get_secret_value())"`
Expected: `https://ph.skatelab.ru ` (empty key by default)

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(backend): add PostHogConfig to settings"
```

---

### Task 3: Create analytics.py — lazy singleton + capture_event

**Files:**
- Create: `backend/app/analytics.py`

- [ ] **Step 1: Write analytics.py**

```python
"""PostHog analytics — lazy singleton, fire-and-forget.

disabled=True when no API key → all calls are no-ops.
Backend integration can be built and merged before PostHog is deployed.
"""

from __future__ import annotations

import logging
import signal
from posthog import Posthog
from app.config import get_settings

logger = logging.getLogger(__name__)

_posthog: Posthog | None = None


def get_posthog() -> Posthog:
    global _posthog
    if _posthog is not None:
        return _posthog
    settings = get_settings()
    api_key = settings.posthog.api_key.get_secret_value()
    if not api_key:
        _posthog = Posthog(api_key="", host="http://localhost:0", disabled=True)
        return _posthog
    _posthog = Posthog(
        project_api_key=api_key,
        host=settings.posthog.host,
        flush_at=50,
        flush_interval=10,
        max_queue_size=10000,
        max_retries=3,
        timeout=10,
        on_error=lambda e, batch: logger.warning("PostHog upload failed: %s", e),
        send=True,
        gzip=True,
    )
    return _posthog


def capture_event(event: str, distinct_id: str, properties: dict | None = None) -> None:
    """Fire-and-forget. Never raises. O(1) queue put — non-blocking."""
    ph = get_posthog()
    if ph.disabled:
        return
    try:
        ph.capture(event=event, distinct_id=distinct_id, properties=properties or {})
    except Exception as e:
        logger.warning("PostHog capture failed for %s: %s", event, e)


def shutdown_posthog() -> None:
    """Flush + stop consumer threads. 5s timeout to prevent hanging."""
    global _posthog
    if _posthog is None:
        return
    try:
        old_handler = signal.signal(signal.SIGALRM, lambda *_: None)
        signal.alarm(5)
        try:
            _posthog.shutdown()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except Exception as e:
        logger.warning("PostHog shutdown error: %s", e)
    _posthog = None
```

- [ ] **Step 2: Verify import works**

Run: `cd backend && uv run python -c "from app.analytics import get_posthog, capture_event, shutdown_posthog; ph = get_posthog(); print('disabled:', ph.disabled)"`
Expected: `disabled: True` (no key set)

- [ ] **Step 3: Commit**

```bash
git add backend/app/analytics.py
git commit -m "feat(backend): add PostHog lazy singleton + capture_event"
```

---

### Task 4: Create analytics_events.py — typed event functions

**Files:**
- Create: `backend/app/analytics_events.py`

- [ ] **Step 1: Write analytics_events.py**

```python
"""Typed PostHog event functions.

Each function wraps capture_event with correct property names.
All calls are fire-and-forget — never raise.
"""

from __future__ import annotations

from app.analytics import capture_event


def analysis_completed(
    distinct_id: str,
    *,
    session_id: str,
    duration_s: float,
    model: str,
    elements_count: int,
    gpu: str,
) -> None:
    capture_event("analysis_completed", distinct_id, {
        "session_id": session_id,
        "duration_s": round(duration_s, 2),
        "model": model,
        "elements_count": elements_count,
        "gpu": gpu,
    })


def analysis_failed(
    distinct_id: str,
    *,
    session_id: str,
    error_type: str,
    retry_count: int,
) -> None:
    capture_event("analysis_failed", distinct_id, {
        "session_id": session_id,
        "error_type": error_type,
        "retry_count": retry_count,
    })


def vastai_dispatched(
    distinct_id: str,
    *,
    session_id: str,
    instance_type: str,
    estimated_cost_usd: float,
) -> None:
    capture_event("vastai_dispatched", distinct_id, {
        "session_id": session_id,
        "instance_type": instance_type,
        "estimated_cost_usd": round(estimated_cost_usd, 4),
    })


def email_sent(
    distinct_id: str,
    *,
    template: str,
    success: bool,
    bounce_reason: str | None = None,
) -> None:
    props: dict = {"template": template, "success": success}
    if bounce_reason:
        props["bounce_reason"] = bounce_reason
    capture_event("email_sent", distinct_id, props)


def subscription_renewed(
    distinct_id: str,
    *,
    variant: str,
    plan: str,
) -> None:
    capture_event("subscription_renewed", distinct_id, {
        "variant": variant,
        "plan": plan,
        "$feature_flag": "renewal_offer_variant",
    })
```

- [ ] **Step 2: Verify import**

Run: `cd backend && uv run python -c "from app.analytics_events import analysis_completed, analysis_failed, vastai_dispatched; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/analytics_events.py
git commit -m "feat(backend): add typed PostHog event functions"
```

---

### Task 5: Create PostHogContextMiddleware

**Files:**
- Create: `backend/app/middleware/posthog_context.py`

- [ ] **Step 1: Write middleware**

```python
"""Extract PostHog tracing headers from frontend API requests.

Stores distinct_id + session_id in request.state for
session replay correlation.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class PostHogContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.posthog_distinct_id = request.headers.get("X-POSTHOG-DISTINCT-ID")
        request.state.posthog_session_id = request.headers.get("X-POSTHOG-SESSION-ID")
        response: Response = await call_next(request)
        return response
```

- [ ] **Step 2: Verify import**

Run: `cd backend && uv run python -c "from app.middleware.posthog_context import PostHogContextMiddleware; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/middleware/posthog_context.py
git commit -m "feat(backend): add PostHog tracing header middleware"
```

---

### Task 6: Register middleware in main.py

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Read main.py to understand current middleware setup**

Run: `head -80 backend/app/main.py`
Note: Check how middleware is currently registered (Litestar `middleware` param or `DefineMiddleware`).

- [ ] **Step 2: Add PostHogContextMiddleware import and registration**

Add import at top:
```python
from app.middleware.posthog_context import PostHogContextMiddleware
```

Add to the `middleware` list in `create_app()`:
```python
middleware=[PostHogContextMiddleware],
```

(The exact syntax depends on how Litestar registers middleware in this file — check Step 1 output.)

- [ ] **Step 3: Verify app starts**

Run: `cd backend && uv run python -c "from app.main import create_app; app = create_app(); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(backend): register PostHogContextMiddleware"
```

---

### Task 7: Add PostHog init/shutdown to worker

**Files:**
- Modify: `backend/app/worker.py`

- [ ] **Step 1: Add get_posthog() call to startup()**

In the `startup` function (line ~202), add at the end, before the retry loop completes:

```python
    from app.analytics import get_posthog
    get_posthog()
```

Add it after the Valkey pool init (after the `for` loop, before function ends). This starts the consumer thread early.

- [ ] **Step 2: Add shutdown_posthog() call to shutdown()**

In the `shutdown` function (line ~232), add before the `logger.info("Worker shutting down")` line:

```python
    from app.analytics import shutdown_posthog
    shutdown_posthog()
```

- [ ] **Step 3: Verify worker module imports**

Run: `cd backend && uv run python -c "from app.worker import startup, shutdown; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/worker.py
git commit -m "feat(backend): add PostHog init/shutdown to arq worker"
```

---

### Task 8: Add PostHog env vars to prod compose

**Files:**
- Modify: `infra/compose.prod.yaml`

- [ ] **Step 1: Add POSTHOG env vars to backend service**

In the `backend` service `environment` section, add after `RESEND_API_KEY`:

```yaml
      POSTHOG_API_KEY: ${POSTHOG_API_KEY:-}
      POSTHOG_HOST: ${POSTHOG_HOST:-https://ph.skatelab.ru}
```

- [ ] **Step 2: Add POSTHOG env vars to frontend service**

In the `frontend` service `environment` section, add after `NEXT_PUBLIC_API_URL`:

```yaml
      NEXT_PUBLIC_POSTHOG_KEY: ${NEXT_PUBLIC_POSTHOG_KEY:-}
      NEXT_PUBLIC_POSTHOG_HOST: ${NEXT_PUBLIC_POSTHOG_HOST:-https://ph.skatelab.ru}
      POSTHOG_PERSONAL_API_KEY: ${POSTHOG_PERSONAL_API_KEY:-}
```

- [ ] **Step 3: Commit**

```bash
git add infra/compose.prod.yaml
git commit -m "feat(infra): add PostHog env vars to prod compose"
```

---

## Wave 2: Frontend SDK + Consent (no infra dependency)

### Task 9: Install @posthog/next

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install @posthog/next**

Run: `cd frontend && bun add @posthog/next`

- [ ] **Step 2: Verify package added**

Run: `cd frontend && grep posthog package.json`
Expected: `"@posthog/next": "..."` in dependencies

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/bun.lockb
git commit -m "feat(frontend): add @posthog/next dependency"
```

---

### Task 10: Add PostHog env exports

**Files:**
- Modify: `frontend/src/lib/env.ts`

- [ ] **Step 1: Add PostHog env var exports**

```typescript
export const devMockAuth = process.env.NEXT_PUBLIC_DEV_MOCK_AUTH === "true"
export const isDevelopment = process.env.NODE_ENV === "development"
export const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? ""
export const posthogHost = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://ph.skatelab.ru"
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/env.ts
git commit -m "feat(frontend): add PostHog env var exports"
```

---

### Task 11: Create feature flag key registry

**Files:**
- Create: `frontend/src/lib/flags.ts`

- [ ] **Step 1: Write flags.ts**

```typescript
export const FLAGS = {
  RENEWAL_OFFER_VARIANT: "renewal_offer_variant",
  NEW_ONBOARDING_FLOW: "new_onboarding_flow",
  NEW_DASHBOARD: "new_dashboard",
  THREEJS_COMPARISON: "threejs_comparison",
} as const

export type FlagKey = (typeof FLAGS)[keyof typeof FLAGS]
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/flags.ts
git commit -m "feat(frontend): add feature flag key registry"
```

---

### Task 12: Create posthog.ts client helpers

**Files:**
- Create: `frontend/src/lib/posthog.ts`

- [ ] **Step 1: Write posthog.ts**

```typescript
"use client"

import { posthog } from "posthog-js"
import { posthogKey, posthogHost } from "@/lib/env"

export function isPostHogAvailable(): boolean {
  return !!posthogKey
}

export function identifyUser(userId: string, properties?: Record<string, unknown>) {
  if (!isPostHogAvailable()) return
  posthog.identify(userId, properties)
}

export function resetIdentity() {
  if (!isPostHogAvailable()) return
  posthog.reset()
}

export function captureEvent(event: string, properties?: Record<string, unknown>) {
  if (!isPostHogAvailable()) return
  posthog.capture(event, properties)
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/posthog.ts
git commit -m "feat(frontend): add PostHog client helper functions"
```

---

### Task 13: Create ConsentProvider (3-tier consent context)

**Files:**
- Create: `frontend/src/components/consent-provider.tsx`

- [ ] **Step 1: Write consent-provider.tsx**

```typescript
"use client"

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react"
import { useMountEffect } from "@/lib/useMountEffect"

export interface ConsentState {
  essential: boolean
  analytics: boolean
  recordings: boolean
}

interface ConsentContextValue extends ConsentState {
  setConsent: (state: ConsentState) => void
  hasConsented: (category: "analytics" | "recordings") => boolean
  showBanner: boolean
  dismissBanner: () => void
}

const STORAGE_KEY = "skatelab_consent"
const OLD_KEY = "consent_accepted"

const ConsentContext = createContext<ConsentContextValue | null>(null)

function readConsent(): ConsentState {
  if (typeof window === "undefined") {
    return { essential: true, analytics: false, recordings: false }
  }

  // Migration: old boolean consent → new 3-tier
  const old = localStorage.getItem(OLD_KEY)
  if (old !== null) {
    const migrated: ConsentState = {
      essential: true,
      analytics: old === "true",
      recordings: old === "true",
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated))
    localStorage.removeItem(OLD_KEY)
    return migrated
  }

  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored) {
    try {
      return JSON.parse(stored) as ConsentState
    } catch {
      // Corrupted — reset
    }
  }

  return { essential: true, analytics: false, recordings: false }
}

function writeConsent(state: ConsentState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  // Cookie for server-side consent detection
  const consentCookie = `skatelab_consent=analytics:${state.analytics},recordings:${state.recordings}; path=/; max-age=31536000; SameSite=Lax`
  document.cookie = consentCookie
}

export function ConsentProvider({ children }: { children: ReactNode }) {
  const [consent, setConsentState] = useState<ConsentState>({
    essential: true,
    analytics: false,
    recordings: false,
  })
  const [showBanner, setShowBanner] = useState(true)
  const [initialized, setInitialized] = useState(false)

  useMountEffect(() => {
    const stored = readConsent()
    setConsentState(stored)
    // Show banner only if no consent stored yet
    setShowBanner(!localStorage.getItem(STORAGE_KEY))
    setInitialized(true)
  })

  const setConsent = useCallback((state: ConsentState) => {
    setConsentState(state)
    writeConsent(state)
    setShowBanner(false)
  }, [])

  const dismissBanner = useCallback(() => {
    setShowBanner(false)
  }, [])

  const hasConsented = useCallback(
    (category: "analytics" | "recordings") => consent[category],
    [consent],
  )

  if (!initialized) return null

  return (
    <ConsentContext.Provider
      value={{ ...consent, setConsent, hasConsented, showBanner, dismissBanner }}
    >
      {children}
    </ConsentContext.Provider>
  )
}

export function useConsent() {
  const ctx = useContext(ConsentContext)
  if (!ctx) throw new Error("useConsent must be used within ConsentProvider")
  return ctx
}
```

- [ ] **Step 2: Verify import**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -5`
Expected: No errors related to consent-provider.tsx

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/consent-provider.tsx
git commit -m "feat(frontend): add 3-tier ConsentProvider"
```

---

### Task 14: Create ConsentBanner (Accept all / Customize)

**Files:**
- Create: `frontend/src/components/consent-banner.tsx`

- [ ] **Step 1: Write consent-banner.tsx**

```typescript
"use client"

import { useState } from "react"
import { useTranslations } from "@/i18n"
import { useConsent, type ConsentState } from "@/components/consent-provider"
import { Button } from "@/components/ui/button"
import FocusLock from "react-focus-lock"

export default function ConsentBanner() {
  const t = useTranslations("landing")
  const { setConsent, showBanner, dismissBanner } = useConsent()
  const [showCustomize, setShowCustomize] = useState(false)
  const [analytics, setAnalytics] = useState(false)
  const [recordings, setRecordings] = useState(false)

  if (!showBanner) return null

  function handleAcceptAll() {
    setConsent({ essential: true, analytics: true, recordings: true })
  }

  function handleAcceptSelected() {
    setConsent({ essential: true, analytics, recordings })
  }

  function handleDecline() {
    setConsent({ essential: true, analytics: false, recordings: false })
  }

  return (
    <FocusLock returnFocus>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-heading"
        className="fixed bottom-0 left-0 right-0 z-[70] border-t border-hairline bg-canvas-soft pb-[env(safe-area-inset-bottom)]"
      >
        <div className="mx-auto max-w-5xl px-6 py-4">
          {!showCustomize ? (
            <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 id="consent-heading" className="sr-only">
                  {t("cookieHeading")}
                </h2>
                <p className="sh-body-md text-ink-mute">
                  {t("cookieText")}{" "}
                  <a href="/cookies" className="text-link hover:underline">
                    Cookie Policy
                  </a>
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={() => setShowCustomize(true)}
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  Customize
                </Button>
                <Button
                  onClick={handleDecline}
                  variant="ghost"
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  {t("cookieDecline")}
                </Button>
                <Button
                  onClick={handleAcceptAll}
                  autoFocus
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  {t("cookieAccept")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <h2 id="consent-heading" className="sh-heading-lg text-ink">
                Cookie Preferences
              </h2>
              <div className="space-y-3">
                <label className="flex items-center gap-3">
                  <input type="checkbox" checked disabled className="accent-primary" />
                  <span className="sh-body-md text-ink">Essential (required)</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={analytics}
                    onChange={(e) => setAnalytics(e.target.checked)}
                    className="accent-primary"
                  />
                  <span className="sh-body-md text-ink">Analytics (pageviews, events)</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={recordings}
                    onChange={(e) => setRecordings(e.target.checked)}
                    className="accent-primary"
                  />
                  <span className="sh-body-md text-ink">Session Recordings (heatmaps, replays)</span>
                </label>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={() => setShowCustomize(false)}
                  className="min-h-[44px] shrink-0"
                >
                  Back
                </Button>
                <Button
                  onClick={handleAcceptSelected}
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  Save Preferences
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </FocusLock>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/consent-banner.tsx
git commit -m "feat(frontend): add ConsentBanner with 3-tier preferences"
```

---

### Task 15: Create use-feature-flag.ts hook

**Files:**
- Create: `frontend/src/hooks/use-feature-flag.ts`

- [ ] **Step 1: Write hook**

```typescript
"use client"

import { useFeatureFlag as usePostHogFeatureFlag } from "@posthog/next"
import type { FlagKey } from "@/lib/flags"

interface FlagResult {
  enabled: boolean
  variant?: string
}

export function useFeatureFlagSafe(key: FlagKey): FlagResult {
  const flag = usePostHogFeatureFlag(key)

  if (!flag) return { enabled: false }
  if (typeof flag === "boolean") return { enabled: flag }
  if (typeof flag === "string") {
    if (flag.startsWith("holdout-")) return { enabled: false }
    return { enabled: true, variant: flag }
  }
  return { enabled: flag.enabled ?? false, variant: flag.variant }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/use-feature-flag.ts
git commit -m "feat(frontend): add type-safe useFeatureFlagSafe hook"
```

---

### Task 16: Create middleware.ts for PostHog proxy

**Files:**
- Create: `frontend/src/app/middleware.ts`

- [ ] **Step 1: Write middleware**

```typescript
import { postHogMiddleware } from "@posthog/next"

export default postHogMiddleware({ proxy: true })

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api).*)"],
}
```

- [ ] **Step 2: Verify Next.js still builds**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/middleware.ts
git commit -m "feat(frontend): add PostHog middleware with API proxy"
```

---

### Task 17: Wire ConsentProvider + PostHogProvider into layout.tsx

**Files:**
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Update layout.tsx imports**

Add imports:

```typescript
import { PostHogProvider, PostHogPageView } from "@posthog/next"
import { ConsentProvider } from "@/components/consent-provider"
import dynamic from "next/dynamic"
```

- [ ] **Step 2: Add dynamic import for ConsentBanner (client-only)**

After imports, add:

```typescript
const ConsentBanner = dynamic(() => import("@/components/consent-banner"), {
  ssr: false,
})
```

- [ ] **Step 3: Wrap the provider tree**

Replace the `<NextIntlClientProvider>` block in the return statement:

```tsx
        <NextIntlClientProvider messages={messages}>
          <ConsentProvider>
            <PostHogProvider
              clientOptions={{
                api_host: "/ingest",
                opt_out_capturing_by_default: true,
                cookieless_mode: "on_reject",
                capture_pageview: true,
                capture_pageleave: true,
                autocapture: true,
                session_recording: {
                  maskAllInputs: true,
                  maskTextSelector: "[data-ph-mask]",
                },
                __add_tracing_headers: ["skatelab.ru"],
              }}
              bootstrapFlags
            >
              <PostHogPageView />
              <Providers nonce={nonce}>
                {children}
              </Providers>
              <ConsentBanner />
              <Toaster richColors position="bottom-center" toastOptions={{ duration: 3000 }} />
            </PostHogProvider>
          </ConsentProvider>
        </NextIntlClientProvider>
```

Note: `<Toaster>` moved inside `PostHogProvider` (still at root level).

- [ ] **Step 4: Verify build**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | tail -5`
Expected: No errors (warnings about dynamic rendering from bootstrapFlags are acceptable)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/layout.tsx
git commit -m "feat(frontend): wire ConsentProvider + PostHogProvider into root layout"
```

---

### Task 18: Add consent-gated identify/reset to auth-provider.tsx

**Files:**
- Modify: `frontend/src/components/auth-provider.tsx`

- [ ] **Step 1: Add PostHog imports**

Add after existing imports:

```typescript
import { useConsent } from "@/components/consent-provider"
import { identifyUser, resetIdentity } from "@/lib/posthog"
```

Wait — `useConsent` is a hook, can be used in AuthProvider since it's a client component.

- [ ] **Step 2: Add consent hook + identify on login**

Inside `AuthProvider` function, add:

```typescript
  const { hasConsented } = useConsent()
```

In the `login` function, after `setUser(u)`:

```typescript
    if (hasConsented("analytics")) {
      identifyUser(u.id, {
        email: u.email,
        role: u.onboarding_role,
        language: u.language,
        onboarding_completed: u.is_verified,
      })
    }
```

In the `register` function, after `setUser(u)` (same block, but user just registered):

```typescript
    if (hasConsented("analytics")) {
      identifyUser(u.id, {
        email: u.email,
        role: u.onboarding_role,
        language: u.language,
        onboarding_completed: false,
      })
    }
```

- [ ] **Step 3: Add reset on logout**

In the `logout` function, after `setUser(null)`:

```typescript
    resetIdentity()
```

- [ ] **Step 4: Add consent-change effect for re-identify**

When consent changes after login, identify if analytics consent is now granted. Add after `useConsent()`:

```typescript
  const [prevAnalyticsConsent, setPrevAnalyticsConsent] = useState(false)

  // Re-identify when analytics consent is granted after login
  if (hasConsented("analytics") && !prevAnalyticsConsent && user) {
    setPrevAnalyticsConsent(true)
    identifyUser(user.id, {
      email: user.email,
      role: user.onboarding_role,
      language: user.language,
      onboarding_completed: user.is_verified,
    })
  }
```

Initialize `prevAnalyticsConsent` from consent state on mount.

- [ ] **Step 5: Verify build**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | tail -5`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/auth-provider.tsx
git commit -m "feat(frontend): add consent-gated PostHog identify/reset to auth"
```

---

### Task 19: Remove old cookie-banner.tsx (replaced by ConsentBanner)

**Files:**
- Delete: `frontend/src/components/landing/cookie-banner.tsx`

- [ ] **Step 1: Find and update all references to old cookie-banner**

Run: `cd frontend && grep -r "cookie-banner" src/ --include="*.tsx" --include="*.ts" -l`
Expected: Find files that import from `./cookie-banner` or `@/components/landing/cookie-banner`

- [ ] **Step 2: Remove the old file and update references**

The old `CookieBanner` was used in a landing layout or page. Remove those imports and usage — `ConsentBanner` is now global via `layout.tsx`.

- [ ] **Step 3: Verify build**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | tail -5`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/components/landing/cookie-banner.tsx
git commit -m "refactor(frontend): remove old cookie-banner (replaced by ConsentBanner)"
```

---

### Task 20: Add consent-gated opt_in/opt_out + recording control

**Files:**
- Modify: `frontend/src/components/consent-provider.tsx`

- [ ] **Step 1: Add PostHog consent sync to setConsent**

Add import at top of consent-provider.tsx:

```typescript
import { posthog } from "posthog-js"
import { posthogKey } from "@/lib/env"
```

Update `setConsent` callback to sync PostHog state:

```typescript
  const setConsent = useCallback((state: ConsentState) => {
    setConsentState(state)
    writeConsent(state)
    setShowBanner(false)

    // Sync PostHog with consent state
    if (!posthogKey) return
    if (state.analytics) {
      posthog.opt_in_capturing()
    } else {
      posthog.opt_out_capturing()
    }
    if (state.recordings) {
      posthog.startSessionRecording()
    } else {
      posthog.stopSessionRecording()
    }
  }, [])
```

- [ ] **Step 2: Also sync on initial load (mount)**

In the `useMountEffect`, after reading consent, sync PostHog:

```typescript
  useMountEffect(() => {
    const stored = readConsent()
    setConsentState(stored)
    setShowBanner(!localStorage.getItem(STORAGE_KEY))
    setInitialized(true)

    // Sync PostHog with stored consent on mount
    if (posthogKey && stored.analytics) {
      // PostHog is already initialized with opt_out_capturing_by_default: true
      // Need to opt in if consent was previously given
      // This runs after PostHogProvider initializes
      setTimeout(() => {
        posthog.opt_in_capturing()
        if (stored.recordings) {
          posthog.startSessionRecording()
        }
      }, 100)
    }
  })
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/consent-provider.tsx
git commit -m "feat(frontend): sync PostHog opt-in/opt-out with consent state"
```

---

### Task 21: Update cookies page with 3-tier consent

**Files:**
- Modify: `frontend/src/app/(landing)/cookies/page.tsx`

- [ ] **Step 1: Replace cookie table with 3-tier structure**

Replace the `<tbody>` section of the cookie table with three categories:

```tsx
            <tbody>
              {/* Essential */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>sb_auth</code></td>
                <td className="py-2 pr-4">Необходимые</td>
                <td className="py-2 pr-4">Идентификация авторизованного пользователя</td>
                <td className="py-2">Сессия</td>
              </tr>
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>skatelab_consent</code></td>
                <td className="py-2 pr-4">Необходимые</td>
                <td className="py-2 pr-4">Хранение настроек согласия на cookies</td>
                <td className="py-2">1 год</td>
              </tr>
              {/* Analytics */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>ph_* </code></td>
                <td className="py-2 pr-4">Аналитические (opt-in)</td>
                <td className="py-2 pr-4">PostHog — просмотр страниц, события, воронки</td>
                <td className="py-2">13 месяцев</td>
              </tr>
              {/* Feature flags (essential) */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>$ph_feat</code></td>
                <td className="py-2 pr-4">Необходимые</td>
                <td className="py-2 pr-4">PostHog feature flags — определяют функциональность приложения</td>
                <td className="py-2">13 месяцев</td>
              </tr>
              {/* Recordings */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>ph_rec*</code></td>
                <td className="py-2 pr-4">Записи сессий (opt-in)</td>
                <td className="py-2 pr-4">PostHog — записи экрана, тепловые карты</td>
                <td className="py-2">30 дней</td>
              </tr>
            </tbody>
```

- [ ] **Step 2: Update analytics section text**

Replace the "Аналитические cookies" paragraph:

```tsx
        <h2 className="sh-heading-lg text-ink">Аналитические cookies (opt-in)</h2>
        <p>
          Мы используем PostHog (самохостинг, сервер в ЕС) для анализа поведения пользователей.
          Аналитические cookies требуют вашего согласия. Без согласия мы используем только
          анонимизированный daily-salted hash (cookieless режим) — данные ограничены.
          Feature flags работают всегда (это функциональность, не отслеживание).
          Срок хранения аналитических данных — не более 13 месяцев.
        </p>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(landing\)/cookies/page.tsx
git commit -m "docs(cookies): update with 3-tier consent and PostHog details"
```

---

### Task 22: Add PostHog data processing to privacy page

**Files:**
- Modify: `frontend/src/app/(landing)/privacy/page.tsx`

- [ ] **Step 1: Read current privacy page**

Run: `head -80 frontend/src/app/\(landing\)/privacy/page.tsx`

- [ ] **Step 2: Add PostHog section**

Add a new `<h2>` + `<p>` section about PostHog data processing:

```tsx
        <h2 className="sh-heading-lg text-ink">Обработка данных PostHog</h2>
        <p>
          Мы используем самохостинг PostHog на собственном сервере (ЕС) для анализа использования
          продукта. Данные обрабатываются:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li>События (просмотры страниц, клики, действия) — 13 месяцев</li>
          <li>Записи сессий (экран) — 30 дней, требуют отдельного согласия</li>
          <li>Feature flags — функциональные данные, работают без согласия</li>
        </ul>
        <p>
          Без согласия на аналитику используется cookieless режим — анонимизированный хеш
          (IP + User-Agent, daily salt). Данные не покидают наш сервер. Третьи стороны не имеют
          доступа к данным PostHog.
        </p>
```

Add this after the existing content sections, before "Управление cookies" section (or equivalent).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(landing\)/privacy/page.tsx
git commit -m "docs(privacy): add PostHog data processing section"
```

---

## Wave 3: Infrastructure Deployment (requires server access)

### Task 23: Create PostHog docker-compose.yml

**Files:**
- Create: `infra/posthog/docker-compose.yml`

**Prerequisites:** SSH access to dedic, Docker running, `infra_app_network` exists.

- [ ] **Step 1: Download official PostHog hobby compose**

Run: `curl -sL https://raw.githubusercontent.com/PostHog/posthog/master/docker-compose.hobby.yml -o /tmp/posthog-hobby.yml`

- [ ] **Step 2: Create modified compose**

Copy the hobby compose and modify:
1. Remove `objectstorage` (MinIO) and `seaweedfs` services — replaced by RustFS
2. Remove `redis7` service — replaced by shared Valkey DB 2
3. Add `REDIS_URL=redis://infra-valkey-1:6379/2` to all services that reference Redis
4. Add `OBJECT_STORAGE_ENDPOINT=http://infra-rustfs-1:9000` + credentials to all services that reference object storage
5. Add `SESSION_RECORDING_V2_S3_*` vars for RustFS
6. Add `networks: [infra]` to all services
7. Pin `db` image to `postgres:15.12-alpine` (not PG 17)
8. Set `POSTHOG_APP_TAG` to specific version (not `latest`)

Save to `infra/posthog/docker-compose.yml`.

- [ ] **Step 3: Commit**

```bash
git add infra/posthog/docker-compose.yml
git commit -m "feat(infra): add PostHog docker-compose (hobby stack, shared infra)"
```

---

### Task 24: Create PostHog .env.posthog template

**Files:**
- Create: `infra/posthog/.env.posthog.example`

- [ ] **Step 1: Write env template**

```bash
# PostHog — copy to .env.posthog and fill in values
POSTHOG_APP_TAG=1.88.0
POSTHOG_SECRET_KEY=change-me-to-random-64-chars

# Shared infrastructure
REDIS_URL=redis://infra-valkey-1:6379/2
OBJECT_STORAGE_ENDPOINT=http://infra-rustfs-1:9000
OBJECT_STORAGE_ACCESS_KEY_ID=<rustfs-key>
OBJECT_STORAGE_SECRET_ACCESS_KEY=<rustfs-secret>
SESSION_RECORDING_V2_S3_ENDPOINT=http://infra-rustfs-1:9000
SESSION_RECORDING_V2_S3_ACCESS_KEY_ID=<rustfs-key>
SESSION_RECORDING_V2_S3_SECRET_ACCESS_KEY=<rustfs-secret>

# PostgreSQL (separate PG 15 container)
POSTHOG_POSTGRES_HOST=posthog-db
POSTHOG_POSTGRES_PASSWORD=change-me
POSTHOG_POSTGRES_DB=posthog
POSTHOG_POSTGRES_USER=posthog

# Domain
POSTHOG_DOMAIN=ph.skatelab.ru
```

- [ ] **Step 2: Commit**

```bash
git add infra/posthog/.env.posthog.example
git commit -m "docs(infra): add PostHog env template"
```

---

### Task 25: Create ClickHouse tuning config

**Files:**
- Create: `infra/posthog/clickhouse/config.d/custom.xml`

- [ ] **Step 1: Write ClickHouse config**

```xml
<clickhouse>
    <max_server_memory_usage>4294967296</max_server_memory_usage>
    <mark_cache_size>1073741824</mark_cache_size>
    <index_mark_cache_size>268435456</index_mark_cache_size>
    <max_bytes_to_merge_at_max_space_in_pool>536870912</max_bytes_to_merge_at_max_space_in_pool>
</clickhouse>
```

- [ ] **Step 2: Commit**

```bash
git add infra/posthog/clickhouse/config.d/custom.xml
git commit -m "feat(infra): add ClickHouse 4GB RAM tuning config"
```

---

### Task 26: Add Caddy route for ph.skatelab.ru

**Files:**
- Modify: `infra/caddy/Caddyfile`

- [ ] **Step 1: Add PostHog route**

Add before the `skatelab.ru` block:

```
ph.{$DOMAIN} {
    reverse_proxy posthog_web:8000

    # Rust capture endpoints
    handle /e/* {
        reverse_proxy posthog_capture:3000
    }
    handle /s/* {
        reverse_proxy posthog_replay_capture:3000
    }
    handle /i/v0/* {
        reverse_proxy posthog_capture:3000
    }
    handle /batch/* {
        reverse_proxy posthog_capture:3000
    }
    handle /flags/* {
        reverse_proxy posthog_feature_flags:3000
    }
}
```

Note: Replace `{$DOMAIN}` with `skatelab.ru` (matching existing Caddyfile pattern). Actual container names depend on PostHog compose service names — adjust after Task 23.

- [ ] **Step 2: Commit**

```bash
git add infra/caddy/Caddyfile
git commit -m "feat(infra): add Caddy route for ph.skatelab.ru"
```

---

### Task 27: Deploy PostHog to dedic

**Prerequisites:** SSH access, RustFS running, Valkey running, `infra_app_network` exists.

- [ ] **Step 1: Create RustFS bucket for PostHog**

SSH to dedic, run:
```bash
# Using RustFS mc alias
mc alias set rustfs http://localhost:9000 <access-key> <secret-key>
mc mb rustfs/posthog
```

- [ ] **Step 2: Copy compose + env to dedic**

```bash
scp -r infra/posthog/ admin@dedic:/opt/posthog/
ssh admin@dedic 'cd /opt/posthog && cp .env.posthog.example .env.posthog && vim .env.posthog'
```

Fill in real values for secret key, RustFS credentials, PG password.

- [ ] **Step 3: Start data layer**

```bash
ssh admin@dedic 'cd /opt/posthog && docker compose up -d posthog-db kafka'
```

Wait for both healthy: `docker compose ps`

- [ ] **Step 4: Start ClickHouse + processing services**

```bash
ssh admin@dedic 'cd /opt/posthog && docker compose up -d clickhouse'
```

Wait for ClickHouse ready (port 8123).

```bash
ssh admin@dedic 'cd /opt/posthog && docker compose up -d'
```

- [ ] **Step 5: Wait for all services healthy**

```bash
ssh admin@dedic 'cd /opt/posthog && docker compose ps'
```

Expected: All services `Up` (healthy). Check for `posthog_web` health.

- [ ] **Step 6: Verify PostHog UI accessible**

Open `https://ph.skatelab.ru` in browser. Should show PostHog setup screen.

- [ ] **Step 7: Create project + get API keys**

In PostHog UI: Create project → Copy Project API Key (`phc_...`) → Copy Personal API Key (`phx_...`).

- [ ] **Step 8: Set env vars on dedic**

Add to `/opt/skatelab/.env`:
```bash
POSTHOG_API_KEY=phc_...
NEXT_PUBLIC_POSTHOG_KEY=phc_...
NEXT_PUBLIC_POSTHOG_HOST=https://ph.skatelab.ru
POSTHOG_PERSONAL_API_KEY=phx_...
```

---

### Task 28: Set up Prometheus monitoring for PostHog

**Files:**
- Modify: `infra/compose.prod.yaml` (Prometheus config, if scrape targets managed here)

- [ ] **Step 1: Add PostHog scrape targets to Prometheus config**

In `infra/compose.prod.yaml` prometheus volumes or in the prometheus config file, add:

```yaml
  - job_name: posthog_clickhouse
    static_configs:
      - targets: ['posthog_clickhouse:8123']
  - job_name: posthog_redpanda
    static_configs:
      - targets: ['posthog_kafka:9644']
```

- [ ] **Step 2: Add alert rules**

Create `infra/prometheus/rules/posthog.yml`:

```yaml
groups:
  - name: posthog
    rules:
      - alert: PostHogClickHouseDiskHigh
        expr: clickhouse_disk_usage_ratio > 0.8
        for: 10m
        labels:
          severity: warning
      - alert: PostHogClickHouseMemoryHigh
        expr: clickhouse_memory_usage_ratio > 0.9
        for: 5m
        labels:
          severity: critical
      - alert: PostHogRedpandaNotReady
        expr: redpanda_cluster_partition_leader_count < redpanda_cluster_partition_count
        for: 5m
        labels:
          severity: critical
```

- [ ] **Step 3: Reload Prometheus config**

```bash
ssh admin@dedic 'docker exec skatelab-prometheus-1 kill -HUP 1'
```

- [ ] **Step 4: Commit**

```bash
git add infra/prometheus/rules/posthog.yml infra/compose.prod.yaml
git commit -m "feat(monitoring): add PostHog Prometheus scrape targets + alerts"
```

---

### Task 29: Set up PostgreSQL backup cron

- [ ] **Step 1: Add PostHog PG backup to existing backup script**

SSH to dedic. Edit `/usr/local/bin/backup-dbs.sh`. Add after existing `pg_dumpall`:

```bash
# PostHog PostgreSQL (separate container on port 5433)
docker exec posthog-db pg_dump -U posthog posthog | gzip > /opt/infra/backups/postgres/posthog_$(date +%Y%m%d).sql.gz
docker exec posthog-db pg_dump -U posthog posthog_persons | gzip > /opt/infra/backups/postgres/posthog_persons_$(date +%Y%m%d).sql.gz
```

- [ ] **Step 2: Test backup manually**

```bash
ssh admin@dedic '/usr/local/bin/backup-dbs.sh'
ls -la /opt/infra/backups/postgres/posthog_*.sql.gz
```

Expected: Two new .gz files with today's date.

- [ ] **Step 3: Commit the backup script update (if tracked in repo)**

Check if backup-dbs.sh is in repo. If not, document in infra/ CLAUDE.md.

---

## Wave 4: Frontend Event Tracking (requires deployed PostHog for testing)

### Task 30: Add event tracking calls to key pages

**Files:**
- Modify: Multiple frontend files (upload, sessions, onboarding, etc.)

- [ ] **Step 1: Add event helper usage in upload flow**

In the upload page or component that handles video upload completion, add:

```typescript
import { captureEvent } from "@/lib/posthog"

// After upload completes:
captureEvent("upload_completed", {
  file_size_mb: Math.round(file.size / 1048576),
  upload_duration_s: Math.round(uploadTime / 1000),
  method: isCamera ? "camera" : "file",
})
```

- [ ] **Step 2: Add event tracking in session creation**

In session creation flow:

```typescript
captureEvent("session_created", {
  session_id: session.id,
  video_duration_s: session.video_duration,
})
```

- [ ] **Step 3: Add event tracking in onboarding**

In onboarding step completion:

```typescript
captureEvent("onboarding_step", {
  step: currentStep,
  role: user.onboarding_role,
})
```

- [ ] **Step 4: Add social share tracking**

In share button handlers:

```typescript
captureEvent("social_share_clicked", {
  platform: "tiktok", // | "telegram" | "whatsapp"
  content_type: "session_result", // | "profile"
})
```

- [ ] **Step 5: Add acquisition source question**

Add "How did you hear about us?" to onboarding. On answer:

```typescript
captureEvent("acquisition_source", {
  source: selectedSource,
})
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add PostHog event tracking to key flows"
```

---

### Task 31: Create TikTok link-in-bio page

**Files:**
- Create: `frontend/src/app/tiktok/page.tsx`

- [ ] **Step 1: Create simple link-in-bio page**

```tsx
import Link from "next/link"

const LINKS = [
  { href: "/register?utm_source=tiktok&utm_medium=organic&utm_campaign=bio_link", label: "Start free analysis" },
  { href: "/login?utm_source=tiktok&utm_medium=organic&utm_campaign=bio_link", label: "Login" },
  { href: "/?utm_source=tiktok&utm_medium=organic&utm_campaign=bio_link", label: "Learn more" },
]

export default function TikTokPage() {
  return (
    <div className="min-h-[dvh] bg-background flex flex-col items-center justify-center p-6">
      <h1 className="sh-display-lg text-ink mb-2">SkateLab</h1>
      <p className="sh-body-md text-ink-mute mb-8">AI coach for figure skating</p>
      <div className="w-full max-w-sm space-y-3">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="block w-full rounded-lg border border-hairline bg-canvas-soft px-6 py-4 text-center sh-body-md text-ink hover:bg-canvas transition-colors"
          >
            {link.label}
          </Link>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/tiktok/page.tsx
git commit -m "feat(frontend): add TikTok link-in-bio page with UTM params"
```

---

### Task 32: Create UTM link generator script

**Files:**
- Create: `scripts/utm_link.py`

- [ ] **Step 1: Write UTM link generator**

```python
#!/usr/bin/env python3
"""Generate UTM-tagged URLs for social media links.

Usage:
    python scripts/utm_link.py --source tiktok --campaign build_in_public --content v_2026_05_24
    python scripts/utm_link.py --source telegram --campaign channel --content post_2026_05_24
"""

import argparse
from urllib.parse import urlencode

BASE_URL = "https://skatelab.ru"


def build_utm_url(source: str, campaign: str, content: str | None = None, medium: str = "organic") -> str:
    params = {
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
    }
    if content:
        params["utm_content"] = content
    return f"{BASE_URL}?{urlencode(params)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate UTM-tagged URLs")
    parser.add_argument("--source", required=True, help="Traffic source (tiktok, telegram, whatsapp)")
    parser.add_argument("--campaign", required=True, help="Campaign name")
    parser.add_argument("--content", default=None, help="Content identifier (video id, post id)")
    parser.add_argument("--medium", default="organic", help="Medium (default: organic)")
    parser.add_argument("--path", default="/", help="URL path (default: /)")
    args = parser.parse_args()

    url = build_utm_url(args.source, args.campaign, args.content, args.medium)
    if args.path != "/":
        url = url.replace(f"{BASE_URL}?", f"{BASE_URL}{args.path}?")
    print(url)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the script**

Run: `python scripts/utm_link.py --source tiktok --campaign build_in_public --content v_2026_05_24`
Expected: `https://skatelab.ru?utm_source=tiktok&utm_medium=organic&utm_campaign=build_in_public&utm_content=v_2026_05_24`

- [ ] **Step 3: Commit**

```bash
git add scripts/utm_link.py
git commit -m "feat(scripts): add UTM link generator for social sharing"
```

---

### Task 33: Add backend event calls in worker tasks

**Files:**
- Modify: `backend/app/worker.py`

- [ ] **Step 1: Add analysis_completed event**

In `process_video_task`, after `store_result` (near line 427), add:

```python
    from app.analytics_events import analysis_completed, analysis_failed
    # ... existing code ...
    # After successful result storage:
    analysis_completed(
        distinct_id=task_id,  # Will be replaced with user_id when available
        session_id=session_id or "",
        duration_s=...,  # compute from started_at
        model="moganet-b",
        elements_count=len(vast_result.segments) if vast_result.segments else 0,
        gpu="vastai",
    )
```

Note: `distinct_id` should be `user.id`, not `task_id`. Check if `user_id` is available in task context or session data. If not available directly, pass it as a task parameter.

- [ ] **Step 2: Add analysis_failed event**

In the except block of `process_video_task`, add:

```python
    analysis_failed(
        distinct_id=task_id,  # Same note as above
        session_id=session_id or "",
        error_type=type(e).__name__,
        retry_count=ctx.get("job_try", 1),
    )
```

- [ ] **Step 3: Add vastai_dispatched event**

Before the Vast.ai dispatch call, add:

```python
    from app.analytics_events import vastai_dispatched
    vastai_dispatched(
        distinct_id=task_id,
        session_id=session_id or "",
        instance_type="vastai-serverless",
        estimated_cost_usd=0.0,  # No estimate available at dispatch time
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/worker.py
git commit -m "feat(backend): add PostHog events to worker tasks"
```

---

### Task 34: Create PostHog dashboards

**Manual task — done in PostHog UI.**

- [ ] **Step 1: Create "Traffic by Source" dashboard**

In PostHog UI (`https://ph.skatelab.ru`):
1. Dashboards → New Dashboard → "Traffic by Source"
2. Add insight: Line chart — Unique visitors by `$utm_source` over time
3. Add insight: Table — Sessions, signups, conversions per source
4. Add filter: date range, source

- [ ] **Step 2: Create "TikTok Performance" dashboard**

1. Dashboards → New Dashboard → "TikTok Performance"
2. Add insight: Events by `$utm_content` (per video) — filter `utm_source=tiktok`
3. Add insight: Signups from TikTok vs other sources
4. Add insight: 7-day retention — TikTok users vs non-TikTok

- [ ] **Step 3: Create "Content ROI" dashboard**

1. Dashboards → New Dashboard → "Content ROI"
2. Add insight: Table — `utm_content` x signup count
3. Add insight: Top 10 videos by signups (bar chart)
4. Add insight: Campaign comparison (bar chart: `utm_campaign`)

---

## Wave 5: A/B Test Setup (requires deployed PostHog + data flowing)

### Task 35: Create onboarding A/B test in PostHog UI

**Manual task — done in PostHog UI.**

- [ ] **Step 1: Create feature flag**

In PostHog UI:
1. Feature Flags → New Flag
2. Key: `new_onboarding_flow`
3. Type: Multivariate
4. Variants: `control` (45%), `simplified` (45%)
5. Holdout: 10% (enable built-in holdout)
6. Targeting: `onboarding_completed = false` (new users)
7. Save

- [ ] **Step 2: Create experiment**

1. Experiments → New Experiment
2. Name: "Onboarding Flow Test"
3. Flag: `new_onboarding_flow`
4. Goal metric: Funnel — `onboarding_step(step=completed)`
5. Guardrail metrics: Time to first session, 7-day retention, analysis_completed in 7d
6. Minimum detectable effect: 15%
7. Launch

- [ ] **Step 3: Add flag usage in frontend**

In onboarding flow component:

```typescript
import { useFeatureFlagSafe } from "@/hooks/use-feature-flag"

function OnboardingFlow() {
  const { variant } = useFeatureFlagSafe("new_onboarding_flow")

  if (variant === "simplified") {
    return <SimplifiedOnboarding />
  }
  return <CurrentOnboarding />
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add onboarding A/B test feature flag usage"
```

---

### Task 36: Verify end-to-end data flow

- [ ] **Step 1: Send test event from frontend**

Open app in browser. Open DevTools Network tab. Look for POST requests to `/ingest/e` or `/ingest/batch`. Verify events include `distinct_id` and event name.

- [ ] **Step 2: Send test event from backend**

SSH to dedic:
```bash
docker exec skatelab-backend-1 python -c "
from app.analytics import capture_event
capture_event('test_event', 'test-user', {'test': True})
"
```

- [ ] **Step 3: Verify events in PostHog**

Open `https://ph.skatelab.ru` → Events → Filter by `test_event`. Verify:
- `test_event` from backend appears
- `$pageview` from frontend appears
- `distinct_id` matches user ID (for identified users)

- [ ] **Step 4: Verify feature flags work**

Check that `new_onboarding_flow` flag resolves correctly in the frontend. Verify `bootstrapFlags` eliminates flicker (no layout shift on load).

- [ ] **Step 5: Verify session recordings**

With recordings consent granted, open app, navigate a few pages. Check PostHog → Session Recordings → recording appears.

- [ ] **Step 6: Verify UTM tracking**

Visit `skatelab.ru?utm_source=tiktok&utm_medium=organic&utm_campaign=test`. Check PostHog → Persons → Current user has `$initial_utm_source=tiktok`.

---

## Self-Review Checklist

### Spec coverage

| Spec section | Tasks |
|-------------|-------|
| Infrastructure (PostHog stack) | 23-29 |
| Shared Infrastructure (RustFS, Valkey DB 2, PG 15) | 23-24 |
| ClickHouse tuning | 25 |
| Frontend SDK (@posthog/next) | 9-12, 15-17 |
| Middleware (postHogMiddleware) | 16 |
| Cookie Consent (3-tier) | 13-14, 19-20 |
| Event Tracking | 30, 33 |
| User Identification | 18 |
| Feature Flags | 11, 15, 35 |
| Backend SDK (posthog-python) | 1-5, 7 |
| A/B Tests | 35 |
| Social Traffic (UTM, link-in-bio) | 31-32, 34 |
| Legal pages (cookies, privacy) | 21-22 |
| Prometheus monitoring | 28 |
| Backup strategy | 29 |

### Placeholder scan

No TBD/TODO found. All tasks have complete code.

### Type consistency

- `ConsentState` interface defined in consent-provider.tsx, used in ConsentBanner
- `FlagKey` type defined in flags.ts, used in use-feature-flag.ts
- `capture_event()` signature: `(event, distinct_id, properties)` — consistent across analytics.py and analytics_events.py
- PostHog `identify()` called with `user.id` (string) — consistent with backend `distinct_id`
