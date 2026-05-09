import * as Sentry from "@sentry/nextjs"

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN
if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV ?? "development",
    tracesSampleRate: 0.1,
    profilesSampleRate: 0.1,
    sendDefaultPii: false,
    // Replay disabled — requires 'unsafe-eval' in CSP which we don't allow in production
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
  })
}
