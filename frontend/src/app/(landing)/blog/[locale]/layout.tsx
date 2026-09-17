import { notFound } from "next/navigation"
import { NextIntlClientProvider } from "next-intl"
import { isLocale } from "@/lib/docs-i18n"
import { PublicShell } from "@/components/landing/public-shell"

export default async function BlogLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  if (!isLocale(locale)) notFound()
  const messages = (await import(`../../../../../messages/${locale}.json`)).default
  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <PublicShell>{children}</PublicShell>
    </NextIntlClientProvider>
  )
}
