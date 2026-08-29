import { cookies } from "next/headers"
import { getRequestConfig } from "next-intl/server"

// #497: allow-list of valid locales. The NEXT_LOCALE cookie is
// user-controllable (no httpOnly, no signature) — without an allow-list,
// any value (e.g. "fr", "xx", or an injected payload) passes through
// and the dynamic import(`../../messages/${locale}.json`) throws
// ERR_MODULE_NOT_FOUND for unsupported locales. Every page 500s
// until the cookie is cleared.
const LOCALES = ["ru", "en"] as const
type Locale = (typeof LOCALES)[number]
const DEFAULT_LOCALE: Locale = "ru"

export default getRequestConfig(async () => {
  const store = await cookies()
  const raw = store.get("NEXT_LOCALE")?.value
  const locale: Locale =
    raw && (LOCALES as readonly string[]).includes(raw) ? (raw as Locale) : DEFAULT_LOCALE

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  }
})
