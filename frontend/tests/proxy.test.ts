import { describe, expect, it } from "vitest"
import { NextRequest, type NextResponse } from "next/server"
import { proxy } from "../src/proxy"

function req(host: string, path = "/") {
  return new NextRequest(new URL(`https://${host}${path}`), {
    headers: { host },
  })
}

describe("public proxy routes", () => {
  it("redirects public auth entry points to the landing page", () => {
    for (const path of ["/login", "/register"]) {
      const response = proxy(req("skatelab.ru", path)) as NextResponse
      expect(response.status).toBe(307)
      expect(response.headers.get("location")).toBe("https://skatelab.ru/")
    }
  })
})
