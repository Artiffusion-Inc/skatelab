"use client"

import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { useAuth } from "@/components/auth-provider"

export function CTASection() {
  const t = useTranslations("landing")
  const { isAuthenticated } = useAuth()

  return (
    <section className="relative mx-auto max-w-[1400px] px-4 py-20 sm:px-6 md:py-32">
      <div
        className="relative overflow-hidden rounded-3xl px-6 py-16 md:px-8 md:py-24 text-center"
        style={{
          background:
            "linear-gradient(135deg, oklch(0.16 0.04 240) 0%, oklch(0.22 0.06 240) 50%, oklch(0.16 0.04 240) 100%)",
        }}
      >
        {/* Ice glow orb behind text */}
        <div
          className="pointer-events-none absolute top-1/2 left-1/2 h-[60%] w-[60%] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-30 blur-3xl"
          style={{ background: "var(--ice-glow)" }}
        />

        {/* Noise texture */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E\")",
          }}
        />

        <div className="relative z-10">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.3em] text-white/50">
            {t("ctaEyebrow")}
          </p>
          <h2 className="mx-auto max-w-2xl text-[clamp(1.75rem,4vw,3rem)] font-medium leading-[1.1] tracking-[-0.02em] text-white">
            {t("ctaHeadline")}
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-sm leading-relaxed text-white/60">
            {t("ctaSubtitle")}
          </p>
          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button
              size="lg"
              className="h-14 rounded-full px-10 text-base font-medium"
              style={{ background: "var(--ice-deep)", color: "white" }}
              asChild
            >
              <a href={isAuthenticated ? "/feed" : "/register"}>
                {isAuthenticated ? t("ctaDashboard") : t("ctaAction")}
              </a>
            </Button>
            {!isAuthenticated && (
              <Button
                variant="ghost"
                size="lg"
                className="h-14 rounded-full border border-white/30 bg-white/15 px-8 text-base font-medium text-white backdrop-blur-sm hover:bg-white/25 hover:text-white"
                asChild
              >
                <a href="/login">{t("ctaLogin")}</a>
              </Button>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
