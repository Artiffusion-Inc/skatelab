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
    : ["'self'", "blob:", "https://s3.skatelab.ru", "https://api.skatelab.ru"]

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

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname === "/login" || request.nextUrl.pathname === "/register") {
    return NextResponse.redirect(new URL("/", request.url))
  }

  const pathname = request.nextUrl.pathname
  const legacyBlog = pathname.match(/^\/(ru|en)\/blog(?:\/(.*))?$/)
  if (request.nextUrl.hostname === "blog.skatelab.ru" || legacyBlog) {
    let path = pathname
    if (legacyBlog) path = `/blog/${legacyBlog[1]}${legacyBlog[2] ? `/${legacyBlog[2]}` : ""}`
    else if (/^\/(ru|en)(\/|$)/.test(path)) path = `/blog${path}`
    else if (!path.startsWith("/blog/"))
      path = `/blog/ru${path === "/" || path === "/blog" ? "" : path}`
    const target = new URL(path, "https://skatelab.ru")
    target.search = request.nextUrl.search
    return NextResponse.redirect(target, 308)
  }

  const requestHeaders = new Headers(request.headers)
  requestHeaders.delete("x-public-locale")
  const blogLocale = pathname.match(/^\/blog\/(ru|en)(?:\/|$)/)?.[1]
  if (blogLocale) requestHeaders.set("x-public-locale", blogLocale)
  if (process.env.NODE_ENV === "development") {
    return NextResponse.next({ request: { headers: requestHeaders } })
  }

  const nonce = crypto.randomUUID().replace(/-/g, "")
  const csp = buildCsp(nonce, false)
  // Next must receive the nonce in request headers to apply it to rendered scripts.
  requestHeaders.set("Content-Security-Policy", csp)
  requestHeaders.set("X-Nonce", nonce)
  const response = NextResponse.next({ request: { headers: requestHeaders } })
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
