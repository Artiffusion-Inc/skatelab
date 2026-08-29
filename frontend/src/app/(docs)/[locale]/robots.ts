import type { MetadataRoute } from "next"

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/internal/"] }],
    sitemap: "https://docs.skatelab.ru/sitemap.xml",
  }
}
