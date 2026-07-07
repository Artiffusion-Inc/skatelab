import path from "node:path"
import withBundleAnalyzer from "@next/bundle-analyzer"
import { withSentryConfig } from "@sentry/nextjs"
import type { NextConfig } from "next"
import createNextIntlPlugin from "next-intl/plugin"
import { createMDX } from "fumadocs-mdx/next"

const nextConfig: NextConfig = {
  output: "standalone",
  images: { unoptimized: true },
  turbopack: { root: path.resolve(__dirname) },
}

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts")

// ponytail: createMDX wraps the base config (innermost), withNextIntl is outer.
// Order per Fumadocs docs: createMDX()(config) then next-intl wraps that.
let config = withBundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
})(withNextIntl(createMDX()(nextConfig)))

if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  config = withSentryConfig(config, { silent: true })
}

export default config
