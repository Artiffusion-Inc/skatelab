export const LOCALES = ["ru", "en"] as const
export type Locale = (typeof LOCALES)[number]
export const DEFAULT_LOCALE: Locale = "ru"

export function isLocale(v: string | undefined): v is Locale {
  return !!v && (LOCALES as readonly string[]).includes(v)
}

export function resolveLocale(seg: string | undefined): Locale {
  return isLocale(seg) ? seg : DEFAULT_LOCALE
}