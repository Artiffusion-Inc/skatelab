import path from "node:path"
import withBundleAnalyzer from "@next/bundle-analyzer"
import { withSentryConfig } from "@sentry/nextjs"
import type { NextConfig } from "next"
import createNextIntlPlugin from "next-intl/plugin"

const nextConfig: NextConfig = {
  output: "standalone",
  images: { unoptimized: true },
  turbopack: { root: path.resolve(__dirname) },
}

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts")

let config = withBundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
})(withNextIntl(nextConfig))

if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  config = withSentryConfig(config, { silent: true })
}

export default config
