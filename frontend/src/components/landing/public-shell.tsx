"use client"

import { usePathname, useSearchParams } from "next/navigation"
import Link from "next/link"
import { ArrowLeft, ArrowUpRight, Menu } from "lucide-react"
import { useLocale, useTranslations } from "@/i18n"
import { setLocale } from "@/i18n/actions"
import { useConsent } from "@/components/consent-provider"
import { TELEGRAM_URL } from "@/lib/public-site"
import { posthogKey } from "@/lib/env"

export function ContactLink({
  children,
  className = "landing-button-signal",
}: {
  children?: React.ReactNode
  className?: string
}) {
  const t = useTranslations("publicSite")
  return (
    <a href={TELEGRAM_URL} className={`landing-button ${className}`}>
      {children ?? t("telegram")}
      <ArrowUpRight size={16} aria-hidden="true" />
    </a>
  )
}

export function PublicShell({
  children,
  home = false,
}: {
  children: React.ReactNode
  home?: boolean
}) {
  const t = useTranslations("publicSite")
  const l = useTranslations("landing")
  const locale = useLocale()
  const pathname = usePathname()
  const phase = useSearchParams().get("phase")
  const { openBanner } = useConsent()
  const links = [
    ["/how-it-works", t("navProcess")],
    ["/equipment", t("navEquipment")],
    [`/blog/${locale}`, t("navBlog")],
    ["/contact", t("navContact")],
  ]
  const homeHref =
    pathname === "/how-it-works"
      ? `/${phase && /^[1-4]$/.test(phase) ? `?phase=${phase}` : ""}#story`
      : pathname === "/equipment"
        ? "/#equipment"
        : pathname.startsWith("/blog")
          ? "/#journal"
          : "/"
  const navLinks = links.map(([href, label]) => (
    <Link
      key={href}
      href={href}
      onClick={event => {
        const menu = event.currentTarget.closest("details")
        if (menu) menu.open = false
      }}
      aria-current={pathname === href || pathname.startsWith(`${href}/`) ? "page" : undefined}
    >
      {label}
    </Link>
  ))
  const blogLocale = pathname.match(/^\/blog\/(ru|en)(\/.*)?$/)
  return (
    <div
      id="top"
      className={`landing-page public-site ${home ? "public-home" : "public-interior"}`}
    >
      <header className="landing-nav">
        <a href="#main-content" className="landing-skip-link">
          {l("skipToContent")}
        </a>
        <div className="landing-nav-inner">
          <Link href="/" className="landing-wordmark" aria-label="SkateLab">
            Skate<span>Lab</span>
          </Link>
          {!home && (
            <Link href={homeHref} className="public-back-link">
              <ArrowLeft size={16} aria-hidden="true" />
              {t("backHome")}
            </Link>
          )}
          <nav className="landing-desktop-nav" aria-label={l("mainNav")}>
            {navLinks}
          </nav>
          <nav className="public-language" aria-label={t("language")}>
            {blogLocale ? (
              <a
                href={`/blog/${blogLocale[1] === "ru" ? "en" : "ru"}${blogLocale[2] ?? ""}`}
                hrefLang={blogLocale[1] === "ru" ? "en" : "ru"}
              >
                {blogLocale[1] === "ru" ? "EN" : "RU"}
              </a>
            ) : (
              <form action={setLocale.bind(null, locale === "ru" ? "en" : "ru")}>
                <button type="submit">{locale === "ru" ? "EN" : "RU"}</button>
              </form>
            )}
          </nav>
          <details
            className="public-mobile-nav"
            onKeyDown={event => {
              if (event.key === "Escape") {
                event.currentTarget.open = false
                event.currentTarget.querySelector("summary")?.focus()
              }
            }}
          >
            <summary aria-label={l("menuOpen")}>
              <Menu aria-hidden="true" />
            </summary>
            <nav aria-label={l("mobileNav")}>
              {navLinks}
              <ContactLink />
            </nav>
          </details>
        </div>
      </header>
      {children}
      <footer className="landing-footer">
        <div className="landing-footer-top">
          <Link href="/" className="landing-wordmark">
            Skate<span>Lab</span>
          </Link>
          <p>{l("footerTagline")}</p>
          <a href={TELEGRAM_URL}>Telegram ↗</a>
        </div>
        <nav className="public-footer-nav" aria-label={t("footerNav")}>
          {navLinks}
          <Link href="/how-it-works#faq">{t("faqTitle")}</Link>
        </nav>
        <div className="landing-footer-bottom">
          <span>{l("footerCopyright")}</span>
          <nav aria-label={l("footerLegal")}>
            <Link href="/privacy">{l("footerPrivacy")}</Link>
            <Link href="/terms">{l("footerTerms")}</Link>
            <Link href="/cookies">{l("footerCookiePolicy")}</Link>
            {posthogKey && (
              <button type="button" onClick={openBanner} className="landing-footer-cookie-settings">
                {l("footerCookieSettings")}
              </button>
            )}
          </nav>
        </div>
      </footer>
    </div>
  )
}

export function ContactClose() {
  const t = useTranslations("publicSite")
  return (
    <section className="public-close">
      <div>
        <p className="public-eyebrow">SkateLab / Telegram</p>
        <h2>{t("closeTitle")}</h2>
        <p>{t("closeBody")}</p>
      </div>
      <ContactLink className="landing-button-paper" />
    </section>
  )
}
