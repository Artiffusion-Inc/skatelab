"use client"

import { useState, useRef, useCallback } from "react"
import { useTranslations } from "@/i18n"
import { Menu, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import FocusLock from "react-focus-lock"

const NAV_ITEMS = [
  { key: "headerNavHowItWorks", href: "#how-it-works" },
  { key: "headerNavPricing", href: "#pricing" },
  { key: "headerNavFaq", href: "#faq" },
] as const

export function StickyHeader() {
  const t = useTranslations("landing")
  const [menuOpen, setMenuOpen] = useState(false)
  const hamburgerRef = useRef<HTMLButtonElement>(null)

  const escHandlerRef = useRef<((e: KeyboardEvent) => void) | null>(null)

  const closeMenu = useCallback(() => {
    setMenuOpen(false)
    document.body.style.overflow = ""
    if (escHandlerRef.current) {
      window.removeEventListener("keydown", escHandlerRef.current)
      escHandlerRef.current = null
    }
  }, [])

  const openMenu = useCallback(() => {
    setMenuOpen(true)
    document.body.style.overflow = "hidden"
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeMenu()
    }
    escHandlerRef.current = onEsc
    window.addEventListener("keydown", onEsc)
  }, [closeMenu])

  const handleNavClick = useCallback(
    (href: string) => {
      closeMenu()
      const el = document.querySelector(href)
      if (el) {
        el.scrollIntoView({ behavior: "smooth" })
        const target = el as HTMLElement
        target.focus({ preventScroll: true })
      }
    },
    [closeMenu],
  )

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 pt-[env(safe-area-inset-top)]"
      style={{ backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
    >
      <div className="header-bg absolute inset-0 bg-background opacity-0" />
      <div className="header-border absolute bottom-0 left-0 right-0 h-px border-b border-hairline opacity-0" />
      <div className="relative mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
        <a href="/" className="sh-body-md text-ink" style={{ fontVariationSettings: '"wght" 600' }}>
          SkateLab
        </a>

        <nav aria-label="Основная навигация" className="hidden md:flex items-center gap-8">
          {NAV_ITEMS.map(item => (
            <button
              type="button"
              key={item.key}
              onClick={() => handleNavClick(item.href)}
              className="sh-body-md text-ink-mute hover:text-ink transition-colors min-h-[44px] flex items-center"
            >
              {t(item.key)}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-4">
          <Button
            variant="default"
            size="sm"
            className="hidden md:inline-flex min-h-[44px]"
            asChild
          >
            <a href="/register">{t("headerCta")}</a>
          </Button>
          <button
            type="button"
            ref={hamburgerRef}
            onClick={openMenu}
            className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="Открыть меню"
            aria-expanded={menuOpen}
          >
            <Menu className="h-6 w-6 text-ink" />
          </button>
        </div>
      </div>

      {menuOpen && (
        <>
          <div
            className="fixed inset-0 z-[55] bg-black/50"
            onClick={closeMenu}
            aria-hidden="true"
          />
          <FocusLock returnFocus disabled={!menuOpen}>
            <div
              className="fixed top-0 right-0 bottom-0 z-[60] bg-background"
              style={{ width: "min(80vw, 280px)" }}
              role="dialog"
              aria-modal="true"
              aria-label="Меню навигации"
            >
              <div className="flex items-center justify-between p-4">
                <span
                  className="sh-body-md text-ink"
                  style={{ fontVariationSettings: '"wght" 600' }}
                >
                  SkateLab
                </span>
                <button
                  type="button"
                  onClick={closeMenu}
                  className="min-h-[44px] min-w-[44px] flex items-center justify-center"
                  aria-label="Закрыть меню"
                >
                  <X className="h-6 w-6 text-ink" />
                </button>
              </div>
              <nav aria-label="Мобильная навигация" className="flex flex-col">
                {NAV_ITEMS.map(item => (
                  <button
                    type="button"
                    key={item.key}
                    onClick={() => handleNavClick(item.href)}
                    className="py-4 px-6 text-lg border-b border-hairline text-ink hover:bg-muted min-h-[44px] text-left"
                  >
                    {t(item.key)}
                  </button>
                ))}
              </nav>
            </div>
          </FocusLock>
        </>
      )}
    </header>
  )
}
