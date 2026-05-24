# PostHog Analytics Integration — Design Spec

**Date:** 2026-05-24
**Status:** Approved
**Scope:** Self-hosted PostHog on existing dedicated server, full feature set (events, session recordings, feature flags, A/B tests)

## Context

SkateLab has no analytics. Sentry handles errors only. The cookies policy already mentions PostHog as a planned integration. Need: user behavior analytics, UX analysis via session recordings, A/B tests for renewal offers, traffic monitoring from organic social (TikTok build-in-public).

## Infrastructure

### PostHog Self-Hosted Stack

Deploy on existing Hetzner dedic (62GB RAM, 16 vCPU, 735GB free disk) alongside existing services.

**Docker Compose services (official PostHog stack):**
- `posthog_web` — Django app (UI + API)
- `posthog_worker` — Celery worker (event processing)
- `posthog_plugin_server` — Plugin execution
- `posthog_clickhouse` — ClickHouse (events storage)
- `posthog_postgres` — PostgreSQL (metadata)
- `posthog_kafka` — Kafka (event pipeline)
- `posthog_redis` — Redis (cache + queue)

**Resource allocation:**
- Total: 8GB RAM limit, 2 CPU cores
- ClickHouse: 4GB RAM
- PostgreSQL: 1GB RAM
- Kafka: 1GB RAM
- Redis: 512MB RAM
- Web + worker + plugin: 1.5GB RAM

### Reverse Proxy

Existing `infra-caddy-1` adds route. Subdomain TBD — `ph.skatelab.ru` assumed, change if different.
```
ph.skatelab.ru {
    reverse_proxy posthog_web:8000
}
```

### Data Retention

| Data type | Retention |
|-----------|-----------|
| Session recordings | 30 days |
| Events | 12 months |
| ClickHouse hot data | 6 months |
| Feature flags history | 12 months |

### Updates

Monthly cadence: `docker compose pull posthog_web posthog_worker posthog_plugin_server && docker compose up -d`

## Frontend Integration

### SDK Setup

`posthog-js` initialized in `app/layout.tsx` (root layout), gated by cookie consent.

```typescript
// lib/posthog.ts
import posthog from 'posthog-js'

export function initPosthog() {
  const consent = getConsentState()
  if (!consent.analytics) return

  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY!, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
    capture_pageview: true,
    capture_pageleave: true,
    autocapture: true,
    persistence: consent.recordings ? 'localStorage' : 'memory',
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: '[data-ph-mask]',
    },
  })

  if (consent.recordings) {
    posthog.startSessionRecording()
  }
}
```

### Env vars (frontend)

```
NEXT_PUBLIC_POSTHOG_KEY=phc_...
NEXT_PUBLIC_POSTHOG_HOST=https://ph.skatelab.ru
```

### Event Tracking

**Autocaptured (no code needed):**
- `$pageview` — all page transitions
- `$autocapture` — clicks on buttons, links, form submissions

**Manual events:**

| Event | Trigger | Properties |
|-------|---------|------------|
| `session_created` | New analysis session created | `session_id`, `video_duration_s` |
| `upload_completed` | Video upload finished | `file_size_mb`, `upload_duration_s`, `method` (camera/file) |
| `analysis_started` | ML pipeline dispatched | `session_id`, `gpu` (local/vastai) |
| `analysis_completed` | Results delivered to user | `session_id`, `duration_s`, `elements_detected` |
| `onboarding_step` | Onboarding step completed | `step`, `role` (coach/skater/parent) |
| `connection_sent` | Coach invites skater | `role` |
| `choreography_created` | Choreography program created | `element_count`, `music_duration_s` |
| `renewal_offer_seen` | Renewal offer displayed | `variant`, `plan` |
| `renewal_offer_clicked` | User clicked renewal CTA | `variant`, `plan` |

### User Identification

```typescript
// After login
posthog.identify(user.id, {
  email: user.email,
  role: user.onboarding_role,
  language: user.language,
  onboarding_completed: user.onboarding_completed,
})

// After logout
posthog.reset()
```

### Cookie Consent (Opt-In)

**3 consent categories:**

| Category | What it enables | Default |
|----------|----------------|---------|
| `essential` | Auth, settings, core functionality | Always on |
| `analytics` | PostHog events, pageviews, funnels | Off until opted in |
| `recordings` | Session recordings, heatmaps | Off until opted in |

**Component: `CookieConsentBanner`**
- Shown on first visit (check `localStorage` for existing consent)
- Two buttons: "Accept all" / "Customize"
- Customize view: toggle per category
- Consent stored in `localStorage` + cookie (`skatelab_consent=analytics:true,recordings:true`)
- On consent change: re-initialize PostHog with new settings

**Behavior:**
- No consent → PostHog NOT initialized, zero tracking
- Analytics consent → `posthog.init()` with `session_recording: false`
- Analytics + recordings → `posthog.init()` with `session_recording: true`

**Legal pages update:**
- `/cookies` — add PostHog to analytics cookies section with categories
- `/privacy` — add PostHog data processing details

## Backend Integration

### SDK Setup

`posthog-python` in `backend/app/`:

```python
# backend/app/analytics.py
from posthog import Posthog

posthog = Posthog(
    api_key=settings.POSTHOG_API_KEY,
    host=settings.POSTHOG_HOST,
    debug=False,
    on_error=lambda e: logger.warning("PostHog error: %s", e),
)
```

### Config

```python
# backend/app/config.py — additions
POSTHOG_API_KEY: str = ""
POSTHOG_HOST: str = "https://ph.skatelab.ru"
```

### Events

| Event | Trigger | Properties |
|-------|---------|------------|
| `analysis_completed` | Worker finishes ML pipeline | `session_id`, `duration_s`, `model`, `elements_count`, `gpu` |
| `analysis_failed` | Pipeline error | `session_id`, `error_type`, `retry_count` |
| `vastai_dispatched` | GPU job sent to Vast.ai | `session_id`, `instance_type`, `estimated_cost_usd` |
| `email_sent` | Resend dispatches email | `template`, `success`, `bounce_reason` |

**Important:** Backend uses same `distinct_id` as frontend (`user.id`) for event unification.

### Failure Handling

PostHog calls are fire-and-forget. SDK batches events (flush every 10s, batch size 50). Queue is in-memory. Analytics failure MUST NOT affect user-facing operations. All PostHog calls wrapped in try/except with logging only.

## A/B Tests

### Feature Flags (PostHog UI → Frontend)

**Renewal offer A/B test:**
- Flag key: `renewal_offer_variant`
- Variants: `control` (no offer), `discount_20` (20% off), `bonus_month` (1 extra month)
- Allocation: 33/33/33
- Targeting: users with `subscription_end < 14 days`
- Conversion event: `renewal_offer_clicked` → `subscription_renewed`

**Onboarding flow A/B:**
- Flag key: `new_onboarding_flow`
- Variants: `control` (current), `simplified` (3-step)
- Allocation: 50/50
- Targeting: new users only
- Conversion: `onboarding_step(step=completed)` completion rate

### Implementation

```typescript
const variant = posthog.getFeatureFlag('renewal_offer_variant')
// variant === 'discount_20' | 'bonus_month' | 'control'
```

PostHog automatically tracks `$feature_flag_called` events with variant info.

## Social Traffic Monitoring

### UTM Strategy

Standard UTM templates for each channel:

| Channel | URL pattern |
|---------|-----------|
| TikTok bio | `?utm_source=tiktok&utm_medium=organic&utm_campaign=build_in_public` |
| TikTok video description | `?utm_source=tiktok&utm_medium=organic&utm_campaign=build_in_public&utm_content={video_id}` |
| Telegram channel | `?utm_source=telegram&utm_medium=organic&utm_campaign=channel` |
| Direct/unknown | PostHog auto-detects from referrer header |

PostHog autocaptures UTM params → `$utm_source`, `$utm_medium`, `$utm_campaign`, `$utm_content`.

### Dashboards

**"Traffic by Source" dashboard:**
- Line chart: unique visitors by `utm_source` over time
- Table: sessions, signups, conversions per source
- Filter: date range, source

**"TikTok Performance" dashboard:**
- Events by `utm_content` (per video)
- Signups from TikTok vs other sources
- Retention: TikTok users vs other users (7-day)

### Custom Event for Sharing

```typescript
posthog.capture('social_share_clicked', {
  platform: 'tiktok', // | 'telegram' | 'whatsapp'
  content_type: 'session_result' | 'profile',
})
```

## Scope Boundaries

**In scope:**
- PostHog self-hosted deployment
- Frontend: posthog-js, event tracking, consent banner, feature flags
- Backend: posthog-python, server-side events
- A/B tests: renewal offers, onboarding flow
- UTM tracking for social traffic
- Legal pages update (cookies, privacy)

**Out of scope:**
- PostHog plugins (third-party integrations)
- Surveys / NPS (add later if needed)
- Data export / ETL to external warehouse
- Custom PostHog dashboards (use defaults, create as needed)
- Mobile app analytics (separate scope when mobile ships)
