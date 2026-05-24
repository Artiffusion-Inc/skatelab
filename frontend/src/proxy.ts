import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

function buildCsp(nonce: string, isDev: boolean): string {
  const scriptSrc = isDev
    ? [
        `'nonce-${nonce}'`,
        "'self'",
        "'unsafe-inline'",
        "'unsafe-eval'",
        "https://cdn.jsdelivr.net",
        "http://localhost:8400",
      ]
    : [`'nonce-${nonce}'`, "'strict-dynamic'", "'unsafe-eval'"]

  const connectSrc = isDev
    ? [
        "'self'",
        "blob:",
        "https://s3.skatelab.ru",
        "http://localhost:8000",
        "ws://localhost:*",
        "http://localhost:8400",
      ]
    : ["'self'", "blob:", "https://s3.skatelab.ru"]

  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": scriptSrc,
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "media-src": ["'self'", "blob:"],
    "connect-src": connectSrc,
    "font-src": ["'self'"],
    "object-src": ["'none'"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "worker-src": ["'self'", "blob:"],
  }

  return Object.entries(directives)
    .map(([key, values]) => `${key} ${values.join(" ")}`)
    .join("; ")
}

export function proxy(_request: NextRequest) {
  const response = NextResponse.next()

  if (process.env.NODE_ENV === "development") {
    return response
  }

  const nonce = crypto.randomUUID().replace(/-/g, "")
  const csp = buildCsp(nonce, false)

  response.headers.set("Content-Security-Policy", csp)
  response.headers.set("X-Nonce", nonce)

  return response
}

export const config = {
  // Skip static assets and Next.js internals — they don't need CSP nonce
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
    },
  ],
}
