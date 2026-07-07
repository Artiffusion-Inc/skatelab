import { describe, it, expect, vi } from "vitest"
import { NextResponse, NextRequest } from "next/server"

// Mock postHog so the middleware can be imported in isolation. Hoisted import
// above is intentional: NextResponse is referenced inside the mock factory.
vi.mock("@posthog/next", () => ({
  postHogMiddleware: () => () => NextResponse.next(),
}))

// Import after mock so the mock applies. vitest hoists vi.mock automatically.
const middlewareModule = await import("../src/app/middleware")
const middleware = middlewareModule.default

function req(host: string, path = "/") {
  return new NextRequest(new URL(`https://${host}${path}`), {
    headers: { host },
  })
}

describe("host-based middleware", () => {
  it("rewrites docs.skatelab.ru to /docs", () => {
    const res = middleware(req("docs.skatelab.ru", "/getting-started")) as NextResponse
    expect(res.headers.get("x-middleware-rewrite")).toContain("/docs")
  })

  it("rewrites blog.skatelab.ru to /blog", () => {
    const res = middleware(req("blog.skatelab.ru", "/my-post")) as NextResponse
    expect(res.headers.get("x-middleware-rewrite")).toContain("/blog")
  })

  it("does not rewrite skatelab.ru", () => {
    const res = middleware(req("skatelab.ru", "/dashboard")) as NextResponse
    expect(res.headers.get("x-middleware-rewrite")).toBeNull()
  })
})
