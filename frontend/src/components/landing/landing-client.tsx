"use client"

import { useEffect, useLayoutEffect, useRef, useState } from "react"
import dynamic from "next/dynamic"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { HeroSection } from "./hero-section"
import { HowItWorksSection } from "./features-section"
import { DemoSection } from "./demo-section"
import { TrustSection } from "./trust-section"
import { PricingSection } from "./pricing-section"
import { FAQSection } from "./faq-section"
import { CTASection } from "./cta-section"
import { FooterSection } from "./footer-section"
import { StickyHeader } from "./sticky-header"
import { MobileCTABar } from "./mobile-cta-bar"

const CookieBanner = dynamic(() => import("./cookie-banner"), { ssr: false })

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger)
}

export function LandingClient() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [showCookieBanner, setShowCookieBanner] = useState(false)

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      const mm = gsap.matchMedia()

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const heroEls = containerRef.current?.querySelectorAll(
          ".hero-eyebrow, .hero-headline, .hero-subtitle, .hero-cta, .hero-scroll"
        )
        if (!heroEls?.length) return

        gsap.fromTo(
          heroEls,
          { opacity: 0, y: 20 },
          {
            opacity: 1,
            y: 0,
            duration: 0.8,
            stagger: 0.12,
            ease: "power2.out",
          }
        )
      })

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const steps = containerRef.current?.querySelectorAll(".hiw-step")
        if (!steps?.length) return

        gsap.fromTo(
          steps,
          { opacity: 0, y: 40 },
          {
            opacity: 1,
            y: 0,
            duration: 0.5,
            stagger: 0.12,
            ease: "power2.out",
            scrollTrigger: {
              trigger: steps[0],
              start: "top 80%",
              toggleActions: "play none none none",
            },
          }
        )
      })

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const cards = containerRef.current?.querySelectorAll(".pricing-card")
        if (!cards?.length) return

        gsap.fromTo(
          cards,
          { opacity: 0, y: 30 },
          {
            opacity: 1,
            y: 0,
            duration: 0.5,
            stagger: 0.12,
            ease: "power2.out",
            scrollTrigger: {
              trigger: cards[0],
              start: "top 85%",
              toggleActions: "play none none none",
            },
          }
        )
      })

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const faqHeader = containerRef.current?.querySelector(".faq-header")
        if (!faqHeader) return

        gsap.fromTo(
          faqHeader,
          { opacity: 0, y: 30 },
          {
            opacity: 1,
            y: 0,
            duration: 0.6,
            ease: "power2.out",
            scrollTrigger: {
              trigger: faqHeader,
              start: "top 90%",
              toggleActions: "play none none none",
            },
          }
        )
      })

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const cta = containerRef.current?.querySelector(".cta-section")
        if (!cta) return

        gsap.fromTo(
          cta,
          { opacity: 0, y: 30 },
          {
            opacity: 1,
            y: 0,
            duration: 0.6,
            ease: "power2.out",
            scrollTrigger: {
              trigger: cta,
              start: "top 85%",
              toggleActions: "play none none none",
            },
          }
        )
      })

      const headerBg = containerRef.current?.querySelector(".header-bg")
      const headerBorder = containerRef.current?.querySelector(".header-border")
      if (headerBg) {
        gsap.to(headerBg, {
          scrollTrigger: {
            trigger: containerRef.current,
            start: "top top",
            end: "bottom top",
            scrub: true,
          },
          opacity: 1,
        })
      }
      if (headerBorder) {
        gsap.to(headerBorder, {
          scrollTrigger: {
            trigger: containerRef.current,
            start: "top top",
            end: "bottom top",
            scrub: true,
          },
          opacity: 1,
        })
      }
    }, containerRef)

    return () => ctx.revert()
  }, [])

  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => {
      if (e.persisted) ScrollTrigger.refresh()
    }
    window.addEventListener("pageshow", onPageShow)
    return () => window.removeEventListener("pageshow", onPageShow)
  }, [])

  useEffect(() => {
    const accepted = localStorage.getItem("consent_accepted")
    if (!accepted) setShowCookieBanner(true)
  }, [])

  const acceptCookies = () => {
    localStorage.setItem("consent_accepted", "true")
    setShowCookieBanner(false)
  }

  const declineCookies = () => {
    localStorage.setItem("consent_accepted", "declined")
    setShowCookieBanner(false)
  }

  return (
    <>
      <div className="landing-page overflow-x-hidden" ref={containerRef}>
        <a
          href="#main-content"
          className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-4 focus-visible:left-4 focus-visible:z-[100] focus-visible:bg-primary focus-visible:text-primary-foreground focus-visible:px-4 focus-visible:py-2 focus-visible:rounded"
        >
          Перейти к основному содержимому
        </a>
        <StickyHeader />
        <main id="main-content" tabIndex={-1}>
          <HeroSection />
          <HowItWorksSection />
          <TrustSection />
          <DemoSection />
          <PricingSection />
          <FAQSection />
          <CTASection />
        </main>
        <FooterSection />
        <MobileCTABar hidden={showCookieBanner} />
      </div>
      {showCookieBanner && <CookieBanner onAccept={acceptCookies} onDecline={declineCookies} />}
    </>
  )
}
