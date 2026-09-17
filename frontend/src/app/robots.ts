import { headers } from "next/headers"
import type { MetadataRoute } from "next"

export default async function robots(): Promise<MetadataRoute.Robots> {
  const host = (await headers()).get("host")?.split(":")[0]
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/internal/",
          "/ru/internal/",
          "/en/internal/",
          "/login",
          "/register",
          "/sessions/",
          "/dashboard",
          "/profile",
          "/settings",
        ],
      },
    ],
    sitemap:
      host === "docs.skatelab.ru"
        ? "https://docs.skatelab.ru/sitemap.xml"
        : "https://skatelab.ru/sitemap.xml",
  }
}
