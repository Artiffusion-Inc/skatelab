"use client"

import { useRef, useLayoutEffect } from "react"
import { useTranslations } from "@/i18n"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

export function TrustSection() {
  const t = useTranslations("landing")
  const sectionRef = useRef<HTMLElement>(null)
  const countersRef = useRef<(HTMLSpanElement | null)[]>([])

  const counters = [
    { valueKey: "trustSessionsValue", labelKey: "trustSessionsLabel", target: 1200, duration: 1.0 },
    { valueKey: "trustSkatersValue", labelKey: "trustSkatersLabel", target: 340, duration: 0.9 },
    { valueKey: "trustClubsValue", labelKey: "trustClubsLabel", target: 15, duration: 0.8 },
  ]

  useLayoutEffect(() => {
    const mm = gsap.matchMedia()

    mm.add("(prefers-reduced-motion: no-preference)", () => {
      countersRef.current.forEach((el, i) => {
        if (!el) return
        const obj = { val: 0 }
        gsap.to(obj, {
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 80%",
            toggleActions: "play none none none",
          },
          val: counters[i].target,
          duration: counters[i].duration,
          ease: "power2.out",
          onUpdate: () => {
            el.textContent = Math.round(obj.val).toLocaleString("ru-RU") + "+"
          },
        })
      })
    })

    return () => mm.revert()
  }, [])

  return (
    <section
      id="trust"
      tabIndex={-1}
      ref={sectionRef}
      className="border-t border-hairline mx-auto max-w-5xl px-6 py-20 md:py-28"
      aria-labelledby="trust-heading"
    >
      <h2 id="trust-heading" className="sr-only">{t("trustTitle")}</h2>
      <div className="grid gap-12 lg:grid-cols-3 text-center">
        {counters.map((counter, i) => (
          <div key={counter.valueKey}>
            <p
              className="sh-display-lg font-bold text-primary"
              aria-label={t(counter.valueKey).replace("+", "") + " " + t(counter.labelKey)}
            >
              <span
                ref={(el) => { countersRef.current[i] = el }}
                aria-hidden="true"
              >
                {t(counter.valueKey)}
              </span>
            </p>
            <p className="mt-2 sh-caption text-ink-mute">{t(counter.labelKey)}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
