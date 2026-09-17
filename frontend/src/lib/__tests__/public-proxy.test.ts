import { NextRequest } from "next/server"
import { describe, expect, it } from "vitest"
import { proxy } from "@/proxy"

describe("actual public proxy", () => {
  it("redirects legacy blog host URLs to the canonical root blog", () => {
    const response = proxy(new NextRequest("https://blog.skatelab.ru/en/blog/recording-guide"))
    expect(response.status).toBe(308)
    expect(response.headers.get("location")).toBe("https://skatelab.ru/blog/en/recording-guide")
  })
  it("forwards explicit blog locale without trusting user-supplied locale headers", () => {
    const response = proxy(
      new NextRequest("https://skatelab.ru/blog/en/recording-guide", {
        headers: { "x-public-locale": "ru" },
      }),
    )
    expect(response.headers.get("x-middleware-request-x-public-locale")).toBe("en")
    const home = proxy(
      new NextRequest("https://skatelab.ru/", { headers: { "x-public-locale": "en" } }),
    )
    expect(home.headers.get("x-middleware-request-x-public-locale")).toBeNull()
  })
  it("does not rewrite documentation routes", () => {
    const response = proxy(new NextRequest("https://docs.skatelab.ru/en/user/getting-started"))
    expect(response.headers.get("x-middleware-rewrite")).toBeNull()
    expect(response.headers.get("location")).toBeNull()
  })
})
