import { headers } from "next/headers"
import type { Metadata, Viewport } from "next"
import { Inter } from "next/font/google"
import { NextIntlClientProvider } from "next-intl"
import { getLocale, getMessages, getTranslations } from "next-intl/server"
import { Toaster } from "@/components/ui/sonner"
import { Providers } from "./providers"
import "./globals.css"

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
  const _nonce = (await headers()).get("x-nonce") ?? ""

  return (
    <html lang={locale} suppressHydrationWarning className={inter.variable}>
      <body className="min-h-screen bg-background text-foreground">
        <NextIntlClientProvider messages={messages}>
          <Providers>
            {children}
            <Toaster richColors position="bottom-center" toastOptions={{ duration: 3000 }} />
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
