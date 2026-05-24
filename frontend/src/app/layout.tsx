import { headers } from "next/headers"
import type { Metadata, Viewport } from "next"
import { Inter } from "next/font/google"
import { NextIntlClientProvider } from "next-intl"
import { getLocale, getMessages, getTranslations } from "next-intl/server"
import { PostHogProvider, PostHogPageView } from "@posthog/next"
import { ConsentProvider } from "@/components/consent-provider"
import { Toaster } from "@/components/ui/sonner"
import { Providers } from "./providers"
import dynamic from "next/dynamic"
import "./globals.css"

const ConsentBanner = dynamic(() => import("@/components/consent-banner"), {
  ssr: false,
})

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
  display: "swap",
})

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
}

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("app")
  return {
    title: t("titleFull"),
    description: "ML-based AI coach for figure skating",
  }
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [locale, messages] = await Promise.all([getLocale(), getMessages()])
  const nonce = (await headers()).get("x-nonce") ?? ""

  return (
    <html lang={locale} suppressHydrationWarning className={inter.variable}>
      <body className="min-h-screen bg-background text-foreground">
        <NextIntlClientProvider messages={messages}>
          <ConsentProvider>
            <PostHogProvider
              clientOptions={{
                api_host: "/ingest",
                opt_out_capturing_by_default: true,
                cookieless_mode: "on_reject",
                capture_pageview: true,
                capture_pageleave: true,
                autocapture: true,
                session_recording: {
                  maskAllInputs: true,
                  maskTextSelector: "[data-ph-mask]",
                },
                __add_tracing_headers: ["skatelab.ru"],
              }}
              bootstrapFlags
            >
              <PostHogPageView />
              <Providers nonce={nonce}>
                {children}
              </Providers>
              <ConsentBanner />
              <Toaster richColors position="bottom-center" toastOptions={{ duration: 3000 }} />
            </PostHogProvider>
          </ConsentProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
