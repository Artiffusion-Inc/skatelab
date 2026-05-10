"use client"

import { useRef, useLayoutEffect, useState, useCallback } from "react"
import Image from "next/image"
import { useTranslations } from "@/i18n"
import { SkeletonPose } from "./skeleton-pose"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

const PHASES = ["demoPhase1Label", "demoPhase2Label", "demoPhase3Label"] as const

export function DemoSection() {
  const t = useTranslations("landing")
  const sectionRef = useRef<HTMLElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const phase1OverlayRef = useRef<HTMLDivElement>(null)
  const skeletonRef = useRef<HTMLDivElement>(null)
  const badgesRef = useRef<HTMLDivElement>(null)
  const [activePhase, setActivePhase] = useState(0)

  useLayoutEffect(() => {
    const mm = gsap.matchMedia()

    mm.add("(min-width: 1024px) and (prefers-reduced-motion: no-preference)", () => {
      if (
        !containerRef.current ||
        !phase1OverlayRef.current ||
        !skeletonRef.current ||
        !badgesRef.current
      )
        return

      gsap.set(skeletonRef.current, { opacity: 0 })
      gsap.set(badgesRef.current, { opacity: 0, y: 10 })

      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: containerRef.current,
          pin: true,
          scrub: 1,
          end: "+=150%",
          anticipatePin: 0.1,
          invalidateOnRefresh: true,
          onUpdate: self => {
            const progress = self.progress
            if (progress < 0.33) setActivePhase(0)
            else if (progress < 0.66) setActivePhase(1)
            else setActivePhase(2)
          },
        },
      })

      tl.to(phase1OverlayRef.current, { opacity: 0, duration: 1 }, 0)
      tl.to(skeletonRef.current, { opacity: 1, duration: 1 }, 1)
      tl.to(badgesRef.current, { opacity: 1, y: 0, duration: 1 }, 2)
    })

    mm.add("(max-width: 1023px), (prefers-reduced-motion: reduce)", () => {
      if (!containerRef.current) return
      gsap.from(containerRef.current, {
        opacity: 0,
        y: 30,
        duration: 0.6,
        scrollTrigger: {
          trigger: containerRef.current,
          start: "top 85%",
          toggleActions: "play none none none",
        },
      })
    })

    return () => mm.revert()
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault()
      setActivePhase(p => Math.min(p + 1, 2))
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault()
      setActivePhase(p => Math.max(p - 1, 0))
    }
  }, [])

  return (
    <section
      id="demo"
      tabIndex={-1}
      ref={sectionRef}
      className="relative border-y border-hairline bg-canvas-soft"
      aria-label={t("demoEyebrow")}
    >
      <div className="relative mx-auto max-w-5xl px-6 py-16 md:py-24">
        <div className="mb-12 md:mb-20 md:pr-32">
          <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-ink-mute">
            {t("demoEyebrow")}
          </p>
          <h2 className="sh-display-xl text-ink">{t("demoHeadline")}</h2>
        </div>

        <div
          ref={containerRef}
          className="hidden lg:block relative mx-auto max-w-4xl overflow-hidden rounded-lg border border-hairline"
        >
          <div className="relative aspect-video">
            <Image
              src="/images/hero-skater.webp"
              alt="Figure skater during a jump, with AI skeleton overlay tracking body position"
              width={1200}
              height={675}
              loading="lazy"
              className="h-full w-full object-cover"
            />
            <div ref={phase1OverlayRef} className="absolute inset-0 sh-demo-overlay" />
            <div className="absolute inset-0 sh-demo-glow" />
            <div ref={skeletonRef}>
              <SkeletonPose role="img" aria-label="AI отслеживает 17 ключевых точек тела" />
            </div>
            <div ref={badgesRef}>
              <div className="absolute top-[12%] left-[8%]">
                <div className="sh-badge-opaque rounded-md px-4 py-3 sh-metric-pulse">
                  <p className="sh-micro uppercase tracking-wider text-on-dark-dim">
                    {t("demoMetricCoM")}
                  </p>
                  <p className="sh-heading-lg text-primary-foreground tabular-nums">1.24 м</p>
                </div>
              </div>
              <div className="absolute right-[10%] bottom-[18%]">
                <div className="sh-badge-opaque rounded-md px-4 py-3 sh-metric-pulse">
                  <p className="sh-micro uppercase tracking-wider text-on-dark-dim">
                    {t("demoMetricRotation")}
                  </p>
                  <p className="sh-heading-lg text-primary-foreground tabular-nums">540°</p>
                </div>
              </div>
              <div className="absolute top-[45%] right-[6%]">
                <div className="sh-badge-opaque rounded-md px-4 py-3 sh-metric-pulse">
                  <p className="sh-micro uppercase tracking-wider text-on-dark-dim">
                    {t("demoMetricAirtime")}
                  </p>
                  <p className="sh-heading-lg text-primary-foreground tabular-nums">0.72 с</p>
                </div>
              </div>
              <div className="sh-badge-opaque absolute bottom-4 left-4 right-4 flex items-center justify-between rounded-sm px-4 py-2">
                <p className="sh-micro text-on-dark-mute">{t("demoSpecPoints")}</p>
                <p className="sh-micro text-on-dark-dim">{t("demoSpecFps")}</p>
              </div>
            </div>
          </div>

          <div
            className="flex items-center justify-center gap-4 py-4"
            role="radiogroup"
            aria-label="Фазы демо"
            onKeyDown={handleKeyDown}
          >
            {PHASES.map((key, i) => (
              <button
                type="button"
                key={key}
                role="radio"
                aria-checked={activePhase === i}
                tabIndex={activePhase === i ? 0 : -1}
                className={`sh-caption px-3 py-1 rounded-full min-h-[44px] ${
                  activePhase === i
                    ? "bg-primary text-primary-foreground"
                    : "text-ink-mute hover:text-ink"
                }`}
                onClick={() => setActivePhase(i)}
              >
                {t(key)}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-4 lg:hidden">
          {PHASES.map((key, i) => (
            <div key={key} className="rounded-lg border border-hairline overflow-hidden">
              <div className="relative aspect-video">
                <Image
                  src="/images/hero-skater.webp"
                  alt=""
                  width={1200}
                  height={675}
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
                {i >= 1 && (
                  <>
                    <div className="absolute inset-0 sh-demo-overlay" />
                    <SkeletonPose role="img" aria-label="AI отслеживает 17 ключевых точек тела" />
                  </>
                )}
                {i === 2 && (
                  <>
                    <div className="absolute top-[12%] left-[8%]">
                      <div className="sh-badge-opaque rounded-md px-3 py-2">
                        <p className="sh-micro uppercase tracking-wider text-on-dark-dim">
                          {t("demoMetricCoM")}
                        </p>
                        <p className="sh-heading-lg text-primary-foreground">1.24 м</p>
                      </div>
                    </div>
                    <div className="absolute right-[10%] bottom-[18%]">
                      <div className="sh-badge-opaque rounded-md px-3 py-2">
                        <p className="sh-micro uppercase tracking-wider text-on-dark-dim">
                          {t("demoMetricRotation")}
                        </p>
                        <p className="sh-heading-lg text-primary-foreground">540°</p>
                      </div>
                    </div>
                    <div className="absolute top-[45%] right-[6%]">
                      <div className="sh-badge-opaque rounded-md px-3 py-2">
                        <p className="sh-micro uppercase tracking-wider text-on-dark-dim">
                          {t("demoMetricAirtime")}
                        </p>
                        <p className="sh-heading-lg text-primary-foreground">0.72 с</p>
                      </div>
                    </div>
                  </>
                )}
              </div>
              <p className="px-4 py-3 sh-caption text-ink">{t(key)}</p>
            </div>
          ))}
        </div>

        <p className="mx-auto mt-8 max-w-xl text-center sh-caption text-ink-mute">
          {t("demoPipelineText")}
        </p>
      </div>
    </section>
  )
}
