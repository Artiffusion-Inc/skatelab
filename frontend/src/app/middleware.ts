import { postHogMiddleware } from "@posthog/next"
import { NextResponse, type NextRequest } from "next/server"

const postHog = postHogMiddleware({ proxy: true })

const DOCS_HOST = "docs.skatelab.ru"
const BLOG_HOST = "blog.skatelab.ru"

export default function middleware(req: NextRequest) {
  // ponytail: nextUrl.hostname over Host header — Host is a forbidden header
  // that happy-dom/edge runtimes may drop; nextUrl.hostname is parsed by Next
  // and port-stripped, works uniformly in dev and prod.
  const host = req.nextUrl.hostname
  if (host === DOCS_HOST) {
    const url = req.nextUrl.clone()
    url.pathname = `/docs${url.pathname}`
    return NextResponse.rewrite(url)
  }
  if (host === BLOG_HOST) {
    const url = req.nextUrl.clone()
    url.pathname = `/blog${url.pathname}`
    return NextResponse.rewrite(url)
  }
  return postHog(req)
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api).*)"],
}
