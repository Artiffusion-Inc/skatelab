# Landing Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the landing page from 4-section MVP to a full 10-section conversion page with GSAP scroll animations, sticky header, pricing, FAQ, footer, cookie banner, and legal pages.

**Architecture:** Next.js App Router route group `(landing)/` forces light theme. Server component `page.tsx` handles auth redirect + renders `<LandingClient />` (single `'use client'` boundary). GSAP ScrollTrigger registered once in `LandingClient` via `useLayoutEffect` + `gsap.context()`. All animations use `gsap.from()` (no-JS safe). JSON-LD schemas rendered server-side.

**Tech Stack:** Next.js 16, React 19, GSAP + ScrollTrigger, Tailwind CSS v4, shadcn/ui, next-intl, next-themes (forcedTheme="light"), react-focus-lock, Lucide React, next/image

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/(landing)/layout.tsx` | Light-only layout, forcedTheme, viewport fit |
| Create | `app/(landing)/page.tsx` | Server component: auth redirect + LandingClient + JSON-LD |
| Move | `app/page.tsx` → deleted | Root page moves into route group |
| Create | `components/landing/landing-client.tsx` | Single client boundary, GSAP orchestration |
| Modify | `components/landing/landing-page.tsx` | Becomes server component wrapper, removed client directive |
| Modify | `components/landing/hero-section.tsx` | Remove CSS animations, use `useRef`, GSAP targets, mobile image, gradient bridge |
| Modify | `components/landing/features-section.tsx` | Rename → HowItWorks, id/anchor, watermark opacity, lg: breakpoint |
| Modify | `components/landing/demo-section.tsx` | 3-phase pinned scroll, matchMedia, keyboard navigation |
| Modify | `components/landing/cta-section.tsx` | Updated copy, "Уже есть аккаунт?" ghost link |
| Modify | `components/landing/skeleton-pose.tsx` | Add `role="img" aria-label` prop, conditional rendering |
| Create | `components/landing/sticky-header.tsx` | Transparent→white header, hamburger menu, focus trap |
| Create | `components/landing/trust-section.tsx` | Animated counters, i18n keys |
| Create | `components/landing/pricing-section.tsx` | 3-tier pricing, Pro highlight, Telegram CTAs |
| Create | `components/landing/faq-section.tsx` | shadcn Accordion, JSON-LD data (not script) |
| Create | `components/landing/footer-section.tsx` | 4-column footer, legal links |
| Create | `components/landing/cookie-banner.tsx` | Focus trap, SSR-safe, localStorage consent |
| Create | `components/landing/mobile-cta-bar.tsx` | Sticky bottom CTA, cookie banner conflict |
| Create | `app/(landing)/privacy/page.tsx` | Privacy Policy (real content) |
| Create | `app/(landing)/terms/page.tsx` | Terms stub |
| Create | `app/(landing)/offer/page.tsx` | Offer stub |
| Create | `app/(landing)/cookies/page.tsx` | Cookie Policy (real content) |
| Create | `app/(landing)/legal-layout.tsx` | Shared legal page layout |
| Modify | `app/globals.css` | Typography weight overrides, sh-price, sh-legal, CSS removals |
| Modify | `app/layout.tsx` | Viewport export, keep root layout for (auth)/(app) |
| Modify | `messages/ru.json` | New i18n keys, key renames |
| Modify | `messages/en.json` | New i18n keys, key renames |
| Modify | `components/landing/index.ts` | Export new components |
| Modify | `package.json` | Add gsap, react-focus-lock |

---

### Task 1: Install Dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install GSAP and react-focus-lock**

Run: `cd frontend && bun add gsap react-focus-lock`

- [ ] **Step 2: Verify installation**

Run: `cd frontend && bunx tsc --noEmit`
Expected: No new type errors from the installed packages

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/bun.lock
git commit -m "chore(frontend): add gsap and react-focus-lock dependencies"
```

---

### Task 2: Route Group Setup — Light-Only Layout

**Files:**
- Create: `frontend/src/app/(landing)/layout.tsx`
- Create: `frontend/src/app/(landing)/page.tsx`
- Delete: `frontend/src/app/page.tsx`

- [ ] **Step 1: Create the landing route group layout**

Create `frontend/src/app/(landing)/layout.tsx`:

```tsx
import { ThemeProvider } from "next-themes"
import type { ReactNode } from "react"

export default function LandingLayout({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" forcedTheme="light" disableTransitionOnChange>
      {children}
    </ThemeProvider>
  )
}
```

- [ ] **Step 2: Create the landing page server component**

Create `frontend/src/app/(landing)/page.tsx`:

```tsx
import type { Metadata } from "next"
import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { getTranslations } from "next-intl/server"
import { LandingClient } from "@/components/landing/landing-client"

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("landing")
  return {
    title: "SkateLab — AI Тренер по фигурному катанию",
    description:
      "Запишите прыжок — увидьте миллиметры. AI-анализ техники: высота ЦМТ, доворот, время полёта. &lt; 15 с на полный разбор видео.",
    alternates: { canonical: "https://skatelab.ru" },
    openGraph: {
      title: "SkateLab — AI Тренер по фигурному катанию",
      description: "Запишите прыжок — увидьте миллиметры. AI-анализ техники за &lt; 15 секунд.",
      url: "https://skatelab.ru",
      siteName: "SkateLab",
      locale: "ru_RU",
      type: "website",
      images: [
        {
          url: "/images/og-image.png",
          width: 1200,
          height: 630,
          alt: "SkateLab — AI анализ фигурного катания",
        },
      ],
    },
  }
}

export default async function LandingPage() {
  const hasAuth = (await cookies()).get("sb_auth")?.value
  if (hasAuth) redirect("/feed")

  const t = await getTranslations("landing")

  const faqItems = [
    { q: t("faqQ1"), a: t("faqA1") },
    { q: t("faqQ2"), a: t("faqA2") },
    { q: t("faqQ3"), a: t("faqA3") },
    { q: t("faqQ4"), a: t("faqA4") },
    { q: t("faqQ5"), a: t("faqA5") },
    { q: t("faqQ6"), a: t("faqA6") },
    { q: t("faqQ7"), a: t("faqA7") },
  ]

  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: faqItems.map((item) => ({
        "@type": "Question",
        name: item.q,
        acceptedAnswer: { "@type": "Answer", text: item.a },
      })),
    },
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "SkateLab",
      url: "https://skatelab.ru",
      logo: "https://skatelab.ru/images/og-image.png",
    },
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: "SkateLab",
      url: "https://skatelab.ru",
    },
  ]

  return (
    <>
      {jsonLd.map((schema, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
      ))}
      <LandingClient />
    </>
  )
}
```

- [ ] **Step 3: Delete old root page.tsx**

Delete `frontend/src/app/page.tsx` (the simple `<LandingPage />` render).

- [ ] **Step 4: Verify the route group works**

Run: `cd frontend && bunx tsc --noEmit`
Expected: No type errors. The `(landing)` route group now owns the `/` route.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/(landing)/ frontend/src/app/page.tsx
git commit -m "feat(frontend): add (landing) route group with light-only layout and auth redirect"
```

---

### Task 3: CSS & Token Amendments

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Add landing-page typography weight overrides AFTER `@layer base` block**

Add after the closing `}` of `@layer base { ... }` (line 477), outside any layer:

```css
/* Landing page typography weight overrides — placed after @layer base for specificity */
body:has(.landing-page) { font-variation-settings: "wght" 400; font-weight: 400; }
.landing-page .sh-display-xxl { font-variation-settings: "wght" 700; font-weight: 700; }
.landing-page .sh-display-xl { font-variation-settings: "wght" 600; font-weight: 600; }
.landing-page .sh-heading-lg { font-variation-settings: "wght" 600; font-weight: 600; }
```

- [ ] **Step 2: Add sh-price and sh-legal classes inside `@layer base`**

Add after the `.sh-micro` class definition (around line 299):

```css
  .sh-price {
    font-size: clamp(2.25rem, 4vw, 3rem);
    font-weight: 700;
    font-variation-settings: "wght" 700;
    line-height: 1;
    letter-spacing: -0.03em;
  }
  .sh-legal {
    font-size: 0.6875rem;
    font-weight: 460;
    font-variation-settings: "wght" 460;
    line-height: 1.5;
  }
```

- [ ] **Step 3: Remove hero CSS animation classes**

Delete these CSS rules from `@layer base`:
- `.hero-eyebrow { opacity: 0; transform: translateY(20px); }`
- `.hero-headline { opacity: 0; transform: translateY(30px); }`
- `.hero-subtitle { opacity: 0; transform: translateY(20px); }`
- `.hero-cta { opacity: 0; transform: translateY(20px); }`
- `.hero-scroll { opacity: 0; }`
- `.hero-visible { animation-fill-mode: forwards; }`
- `.hero-visible.hero-eyebrow { ... }`
- `.hero-visible.hero-headline { ... }`
- `.hero-visible.hero-subtitle { ... }`
- `.hero-visible.hero-cta { ... }`
- `.hero-visible.hero-scroll { ... }`
- `@keyframes fadeUp { ... }`
- `@keyframes fadeIn { ... }`

Also remove the reduced-motion overrides for these classes (the `@media (prefers-reduced-motion: reduce)` block referencing `.hero-eyebrow`, `.hero-headline`, etc.). Keep the global reduced-motion rule.

- [ ] **Step 4: Update color tokens**

In `:root`:
- Change `--on-dark-faint: oklch(0.42 0.03 280)` → `oklch(0.6 0.03 280)`
- Change `.sh-badge-opaque` background: `oklch(0.14 0.06 280 / 0.85)` → `oklch(0.14 0.06 280 / 0.92)`
- Change `.sh-badge-flat` background: `oklch(0.14 0.06 280 / 0.85)` → `oklch(0.14 0.06 280 / 0.92)`
- Change `.step-watermark` color: `oklch(0.85 0.006 80 / 0.15)` → `oklch(0.7 0.006 80 / 0.25)`

- [ ] **Step 5: Add global reduced-motion rule and scroll-margin rule**

Add inside `@layer base`:

```css
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
    }
  }

  section[id] {
    scroll-margin-top: 5rem;
  }
```

- [ ] **Step 6: Verify CSS compiles**

Run: `cd frontend && bunx tsc --noEmit`
Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat(frontend): add landing typography overrides, remove hero CSS animations, update color tokens"
```

---

### Task 4: i18n Migration — Key Renames & New Keys

**Files:**
- Modify: `frontend/messages/ru.json`
- Modify: `frontend/messages/en.json`

- [ ] **Step 1: Add new i18n keys to `ru.json` landing section**

Add after `ctaDashboard` key:

```json
    "howItWorksTitle": "Как это работает",
    "howItWorksHeadline": "Три шага от видео до рекомендаций",
    "howItWorksStep1Title": "Загрузите видео",
    "howItWorksStep1Desc": "Снимите элемент на телефон. MP4, MOV, WebM до 500 МБ. Результат за секунды.",
    "howItWorksStep1Accent": "Никаких специальных камер или настроек",
    "howItWorksStep2Title": "Получите разбор",
    "howItWorksStep2Desc": "Высота прыжка, время полёта, скорость доворота, стабильность приземления. В числах, графиках и рекомендациях.",
    "howItWorksStep2Accent": "12+ параметров по каждому кадру",
    "howItWorksStep3Title": "Сравните с эталоном",
    "howItWorksStep3Desc": "Выравнивание по профессиональным референсам. Точно видите, где теряете высоту и скорость.",
    "howItWorksStep3Accent": "Объективные данные для тренера и ученика",
    "trustTitle": "Нам доверяют",
    "trustSessionsValue": "1,200+",
    "trustSessionsLabel": "сессий проанализировано",
    "trustSkatersValue": "340+",
    "trustSkatersLabel": "фигуристов",
    "trustClubsValue": "15+",
    "trustClubsLabel": "клубов",
    "demoPhase1Label": "1. Исходное видео",
    "demoPhase2Label": "2. Скелетон тела",
    "demoPhase3Label": "3. Биомеханические метрики",
    "demoPipelineText": "Видео → Скелетон → Метрики за 12 секунд",
    "pricingTitle": "Тарифы",
    "pricingFreeName": "Free",
    "pricingFreePrice": "0 ₽/мес",
    "pricingFreeDesc": "Для начинающих",
    "pricingFreeFeatures": "3 анализа в месяц|Базовый скелетон",
    "pricingFreeCta": "Начать бесплатно",
    "pricingProName": "Pro",
    "pricingProPrice": "990 ₽/мес",
    "pricingProDesc": "Для фигуристов",
    "pricingProBadge": "Популярный",
    "pricingProFeatures": "Безлимит анализов|Рекомендации|Прогресс|Сравнение с эталоном",
    "pricingProCta": "Попробовать Pro",
    "pricingCoachName": "Coach",
    "pricingCoachPrice": "3,500 ₽/мес",
    "pricingCoachDesc": "Для тренеров",
    "pricingCoachFeatures": "Dashboard учеников|Диагностика|Отчёты|До 20 учеников",
    "pricingCoachCta": "Связаться с нами",
    "faqTitle": "Вопросы и ответы",
    "faqQ1": "Нужна ли специальная камера?",
    "faqA1": "Нет, достаточно телефона. MP4, MOV, WebM до 500 МБ.",
    "faqQ2": "Какие элементы распознаются?",
    "faqA2": "8 элементов: тройка, вальсовый, перекидной, флип, сальхов, петля, лютц, аксель.",
    "faqQ3": "Нужен ли датчик или IMU?",
    "faqA3": "Нет. Видеоанализ работает без дополнительного оборудования. IMU-датчики — опциональное улучшение точности.",
    "faqQ4": "Насколько точны метрики?",
    "faqA4": "Точность высоты ЦМТ ±2 см, доворота ±5°. Основано на centre-of-mass траектории, не времени полёта.",
    "faqQ5": "Сколько стоит?",
    "faqA5": "Бесплатно 3 анализа в месяц. Pro — 990 ₽/мес за безлимит. Для тренеров — от 3,500 ₽/мес. См. Тарифы для подробностей.",
    "faqQ6": "Данные хранятся безопасно?",
    "faqA6": "Видео хранятся в зашифрованном хранилище. Биометрические данные обрабатываются с вашего отдельного согласия.",
    "faqQ7": "Есть ли мобильное приложение?",
    "faqA7": "Веб-приложение работает на любом устройстве. Мобильное приложение — в планах.",
    "footerTagline": "Твой прыжок в цифрах",
    "footerCopyright": "© 2026 SkateLab. Все права защищены.",
    "footerProduct": "Продукт",
    "footerLegal": "Правовая информация",
    "footerContact": "Контакты",
    "footerPrivacy": "Политика конфиденциальности",
    "footerTerms": "Пользовательское соглашение",
    "footerOffer": "Оферта",
    "footerCookiePolicy": "Cookie Policy",
    "footerHowItWorks": "Как это работает",
    "footerPricing": "Тарифы",
    "footerFaq": "FAQ",
    "cookieHeading": "Согласие на использование файлов cookie",
    "cookieText": "Мы используем cookies для работы сервиса. Продолжая, вы соглашаетесь с Cookie Policy.",
    "cookieAccept": "Принять",
    "headerNavHowItWorks": "Как это работает",
    "headerNavPricing": "Тарифы",
    "headerNavFaq": "FAQ",
    "headerCta": "Начать бесплатно",
    "skipToContent": "Перейти к основному содержимому",
    "ctaSubtitleNew": "Первый анализ — бесплатно. Без подписки, без обязательств.",
    "ctaHasAccount": "Уже есть аккаунт?",
    "ctaHeadlineNew": "Тренируй по данным, а не на ощущениях"
```

- [ ] **Step 2: Update ctaSecondary value in `ru.json`**

Change `"ctaSecondary": "Как это работает"` → `"ctaSecondary": "Смотреть демо"`

- [ ] **Step 3: Add new i18n keys to `en.json` landing section**

Add after `ctaDashboard` key:

```json
    "howItWorksTitle": "How it works",
    "howItWorksHeadline": "Three steps from video to recommendations",
    "howItWorksStep1Title": "Upload video",
    "howItWorksStep1Desc": "Film an element on your phone. MP4, MOV, WebM up to 500 MB. Results in seconds.",
    "howItWorksStep1Accent": "No special cameras or setups needed",
    "howItWorksStep2Title": "Get the breakdown",
    "howItWorksStep2Desc": "Jump height, airtime, rotation speed, landing stability. In numbers, charts, and recommendations.",
    "howItWorksStep2Accent": "12+ parameters per frame",
    "howItWorksStep3Title": "Compare to reference",
    "howItWorksStep3Desc": "Alignment against professional references. See exactly where you lose height and speed.",
    "howItWorksStep3Accent": "Objective data for coach and skater",
    "trustTitle": "Trusted by",
    "trustSessionsValue": "1,200+",
    "trustSessionsLabel": "sessions analyzed",
    "trustSkatersValue": "340+",
    "trustSkatersLabel": "skaters",
    "trustClubsValue": "15+",
    "trustClubsLabel": "clubs",
    "demoPhase1Label": "1. Raw video",
    "demoPhase2Label": "2. Body skeleton",
    "demoPhase3Label": "3. Biomechanical metrics",
    "demoPipelineText": "Video → Skeleton → Metrics in 12 seconds",
    "pricingTitle": "Pricing",
    "pricingFreeName": "Free",
    "pricingFreePrice": "0 ₽/mo",
    "pricingFreeDesc": "For beginners",
    "pricingFreeFeatures": "3 analyses per month|Basic skeleton",
    "pricingFreeCta": "Start for free",
    "pricingProName": "Pro",
    "pricingProPrice": "990 ₽/mo",
    "pricingProDesc": "For skaters",
    "pricingProBadge": "Popular",
    "pricingProFeatures": "Unlimited analyses|Recommendations|Progress|Reference comparison",
    "pricingProCta": "Try Pro",
    "pricingCoachName": "Coach",
    "pricingCoachPrice": "3,500 ₽/mo",
    "pricingCoachDesc": "For coaches",
    "pricingCoachFeatures": "Student dashboard|Diagnostics|Reports|Up to 20 students",
    "pricingCoachCta": "Contact us",
    "faqTitle": "FAQ",
    "faqQ1": "Do I need a special camera?",
    "faqA1": "No, a phone is enough. MP4, MOV, WebM up to 500 MB.",
    "faqQ2": "Which elements are recognized?",
    "faqA2": "8 elements: toe loop, waltz jump, salchow, flip, loop, lutz, axel, euler.",
    "faqQ3": "Do I need a sensor or IMU?",
    "faqA3": "No. Video analysis works without additional equipment. IMU sensors are an optional accuracy improvement.",
    "faqQ4": "How accurate are the metrics?",
    "faqA4": "CoM height accuracy ±2 cm, under-rotation ±5°. Based on center-of-mass trajectory, not flight time.",
    "faqQ5": "How much does it cost?",
    "faqA5": "Free for 3 analyses per month. Pro — 990 ₽/mo for unlimited. For coaches — from 3,500 ₽/mo. See Pricing for details.",
    "faqQ6": "Is my data stored securely?",
    "faqA6": "Videos are stored in encrypted storage. Biometric data is processed with your separate consent.",
    "faqQ7": "Is there a mobile app?",
    "faqA7": "The web app works on any device. A mobile app is planned.",
    "footerTagline": "Your jump in numbers",
    "footerCopyright": "© 2026 SkateLab. All rights reserved.",
    "footerProduct": "Product",
    "footerLegal": "Legal",
    "footerContact": "Contact",
    "footerPrivacy": "Privacy Policy",
    "footerTerms": "Terms of Service",
    "footerOffer": "Offer",
    "footerCookiePolicy": "Cookie Policy",
    "footerHowItWorks": "How it works",
    "footerPricing": "Pricing",
    "footerFaq": "FAQ",
    "cookieHeading": "Cookie consent",
    "cookieText": "We use cookies to operate the service. By continuing, you agree to the Cookie Policy.",
    "cookieAccept": "Accept",
    "headerNavHowItWorks": "How it works",
    "headerNavPricing": "Pricing",
    "headerNavFaq": "FAQ",
    "headerCta": "Start for free",
    "skipToContent": "Skip to content",
    "ctaSubtitleNew": "First analysis is free. No subscription, no commitment.",
    "ctaHasAccount": "Already have an account?",
    "ctaHeadlineNew": "Train on data, not on feelings"
```

- [ ] **Step 4: Update ctaSecondary value in `en.json`**

Change `"ctaSecondary": "How it works"` → `"ctaSecondary": "Watch demo"`

- [ ] **Step 5: Verify JSON is valid**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('messages/ru.json','utf8')); JSON.parse(require('fs').readFileSync('messages/en.json','utf8')); console.log('OK')" `
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): add landing page i18n keys for new sections"
```

---

### Task 5: LandingClient — GSAP Orchestrator

**Files:**
- Create: `frontend/src/components/landing/landing-client.tsx`
- Modify: `frontend/src/components/landing/landing-page.tsx`

- [ ] **Step 1: Create LandingClient**

Create `frontend/src/components/landing/landing-client.tsx`:

```tsx
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

      // Hero entrance
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const heroEls = containerRef.current?.querySelectorAll(
          ".hero-eyebrow, .hero-headline, .hero-subtitle, .hero-cta, .hero-scroll"
        )
        if (!heroEls?.length) return

        gsap.set(heroEls, { opacity: 0, y: 20 })
        gsap.from(heroEls, {
          opacity: 0,
          y: 20,
          duration: 0.8,
          stagger: 0.12,
          ease: "power2.out",
        })
      })

      // How It Works entrance
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const steps = containerRef.current?.querySelectorAll(".hiw-step")
        if (!steps?.length) return

        gsap.from(steps, {
          scrollTrigger: {
            trigger: steps[0],
            start: "top 80%",
            toggleActions: "play none none none",
          },
          opacity: 0,
          y: 40,
          duration: 0.5,
          stagger: 0.12,
          ease: "power2.out",
        })
      })

      // Trust counters — handled inside TrustSection via ref callback

      // Pricing entrance
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const cards = containerRef.current?.querySelectorAll(".pricing-card")
        if (!cards?.length) return

        gsap.from(cards, {
          scrollTrigger: {
            trigger: cards[0],
            start: "top 85%",
            toggleActions: "play none none none",
          },
          opacity: 0,
          y: 30,
          duration: 0.5,
          stagger: 0.12,
          ease: "power2.out",
        })
      })

      // FAQ header entrance
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const faqHeader = containerRef.current?.querySelector(".faq-header")
        if (!faqHeader) return

        gsap.from(faqHeader, {
          scrollTrigger: {
            trigger: faqHeader,
            start: "top 90%",
            toggleActions: "play none none none",
          },
          opacity: 0,
          y: 30,
          duration: 0.6,
          ease: "power2.out",
        })
      })

      // CTA entrance
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const cta = containerRef.current?.querySelector(".cta-section")
        if (!cta) return

        gsap.from(cta, {
          scrollTrigger: {
            trigger: cta,
            start: "top 85%",
            toggleActions: "play none none none",
          },
          opacity: 0,
          y: 30,
          duration: 0.6,
          ease: "power2.out",
        })
      })

      // Header background on scroll
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

  // bfcache restoration
  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => {
      if (e.persisted) ScrollTrigger.refresh()
    }
    window.addEventListener("pageshow", onPageShow)
    return () => window.removeEventListener("pageshow", onPageShow)
  }, [])

  // Cookie banner — SSR safe
  useEffect(() => {
    const accepted = localStorage.getItem("consent_accepted")
    if (!accepted) setShowCookieBanner(true)
  }, [])

  const acceptCookies = () => {
    localStorage.setItem("consent_accepted", "true")
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
      {showCookieBanner && <CookieBanner onAccept={acceptCookies} />}
    </>
  )
}
```

- [ ] **Step 2: Simplify landing-page.tsx (server wrapper, no longer primary entry)**

Since `LandingClient` imports sections directly, `landing-page.tsx` becomes unused. Delete it or simplify it. For clean migration, update `frontend/src/components/landing/index.ts` to export `LandingClient` instead:

```tsx
export { LandingClient } from "./landing-client"
export { HeroSection } from "./hero-section"
export { HowItWorksSection as FeaturesSection } from "./features-section"
export { DemoSection } from "./demo-section"
export { CTASection } from "./cta-section"
export { SkeletonPose } from "./skeleton-pose"
export { TrustSection } from "./trust-section"
export { PricingSection } from "./pricing-section"
export { FAQSection } from "./faq-section"
export { FooterSection } from "./footer-section"
export { StickyHeader } from "./sticky-header"
export { CookieBanner } from "./cookie-banner"
export { MobileCTABar } from "./mobile-cta-bar"
```

Delete `frontend/src/components/landing/landing-page.tsx`.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit`
Expected: Errors only from missing new component files (StickyHeader, TrustSection, etc.) — these will be created in subsequent tasks.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/landing/landing-client.tsx frontend/src/components/landing/index.ts frontend/src/components/landing/landing-page.tsx
git commit -m "feat(frontend): add LandingClient GSAP orchestrator, update barrel exports"
```

---

### Task 6: Hero Section Rewrite

**Files:**
- Modify: `frontend/src/components/landing/hero-section.tsx`
- Modify: `frontend/src/components/landing/skeleton-pose.tsx`

- [ ] **Step 1: Update SkeletonPose to accept aria props**

Modify `frontend/src/components/landing/skeleton-pose.tsx`:

```tsx
"use client"

import { useState } from "react"
import { useMountEffect } from "@/lib/useMountEffect"

const BASE_POINTS = [
  { x: 0.5, y: 0.15 },
  { x: 0.5, y: 0.3 },
  { x: 0.38, y: 0.32 },
  { x: 0.3, y: 0.48 },
  { x: 0.22, y: 0.62 },
  { x: 0.62, y: 0.32 },
  { x: 0.7, y: 0.48 },
  { x: 0.78, y: 0.62 },
  { x: 0.5, y: 0.52 },
  { x: 0.42, y: 0.68 },
  { x: 0.36, y: 0.85 },
  { x: 0.32, y: 0.98 },
  { x: 0.58, y: 0.68 },
  { x: 0.64, y: 0.85 },
  { x: 0.68, y: 0.98 },
]

const LINES: readonly [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [1, 5], [5, 6], [6, 7],
  [1, 8], [8, 9], [9, 10], [10, 11],
  [8, 12], [12, 13], [13, 14],
] as const

interface SkeletonPoseProps {
  role?: string
  "aria-label"?: string
}

export function SkeletonPose({ role, "aria-label": ariaLabel }: SkeletonPoseProps) {
  const [frame, setFrame] = useState(0)

  useMountEffect(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % 60), 50)
    return () => clearInterval(id)
  })

  const points = BASE_POINTS.map((p, i) => {
    const offset = Math.sin((frame + i * 10) * 0.1) * 0.015
    return { x: p.x + offset, y: p.y + offset * 0.5 }
  })

  const isDecorative = !role

  return (
    <svg
      viewBox="0 0 1 1"
      className="absolute inset-0 h-full w-full"
      role={isDecorative ? undefined : role}
      aria-label={isDecorative ? undefined : ariaLabel}
      aria-hidden={isDecorative}
    >
      {LINES.map(([a, b]) => (
        <line
          key={`${a}-${b}`}
          x1={points[a].x}
          y1={points[a].y}
          x2={points[b].x}
          y2={points[b].y}
          stroke="rgba(255,255,255,0.9)"
          strokeWidth="0.008"
          strokeLinecap="round"
        />
      ))}
      {points.map((p, i) => (
        <circle
          key={`pt-${i}`}
          cx={p.x}
          cy={p.y}
          r="0.012"
          fill="rgba(255,255,255,0.95)"
        />
      ))}
    </svg>
  )
}
```

- [ ] **Step 2: Rewrite hero-section.tsx**

Remove `useState(mounted)`, CSS animation classes, Unsplash `<img>`. Add GSAP class targets, `next/image`, mobile image, gradient bridge:

```tsx
"use client"

import Image from "next/image"
import { useTranslations } from "@/i18n"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import { SkeletonPose } from "./skeleton-pose"

export function HeroSection() {
  const t = useTranslations("landing")
  const { isAuthenticated } = useAuth()

  return (
    <section className="hero-section relative flex min-h-[100dvh] items-center overflow-hidden bg-primary" aria-label={t("eyebrow")}>
      <div className="sh-violet-backdrop absolute inset-0" />

      <div className="relative z-10 mx-auto w-full max-w-5xl px-6 py-8 sm:py-16 lg:py-0">
        <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
          <div className="text-left">
            <p className="hero-eyebrow mb-5 sh-micro uppercase tracking-[0.3em] text-on-dark-mute">
              {t("eyebrow")}
            </p>

            <h1 className="hero-headline sh-display-xxl text-primary-foreground">
              {t("headline")}
              <br />
              <span className="text-surface-violet-soft">{t("headlineLine2")}</span>
            </h1>

            <p className="hero-subtitle mt-5 max-w-2xl sh-body-lg text-on-dark-mute">
              {t("subtitle")}
            </p>

            <div className="hero-cta mt-3 flex items-baseline gap-2">
              <span className="sh-display-lg font-bold text-surface-violet-soft">
                {t("heroStatValue")}
              </span>
              <span className="sh-caption text-on-dark-mute">
                {t("heroStatLabel")}
              </span>
            </div>

            <div className="hero-cta mt-8 flex flex-col items-start gap-4 sm:flex-row">
              <Button
                variant="on-dark-pill"
                size="lg"
                className="min-h-[44px] px-10 text-base"
                asChild
              >
                <a href={isAuthenticated ? "/feed" : "/register"}>{t("ctaPrimary")}</a>
              </Button>
              <Button
                variant="ghost"
                size="lg"
                className="min-h-[44px] rounded-full px-8 text-base text-on-dark-mute hover:text-primary-foreground"
                asChild
              >
                <a href="#demo">{t("ctaSecondary")}</a>
              </Button>
            </div>
          </div>

          <div className="relative order-2">
            <div className="relative aspect-[16/9] overflow-hidden rounded-lg lg:aspect-[4/5]">
              <Image
                src="/images/hero-skater.webp"
                alt="Figure skater performing a jump on ice"
                width={800}
                height={1000}
                priority
                className="h-full w-full object-cover"
              />
              <div className="absolute inset-0 bg-primary/40" />
              <SkeletonPose
                role="img"
                aria-label="AI отслеживает 17 ключевых точек тела"
              />
              <div className="sh-badge-opaque absolute top-[15%] right-[8%] rounded-md px-4 py-3 max-sm:hidden">
                <p className="sh-micro uppercase tracking-wider text-on-dark-faint">
                  {t("heroOverlayLabel")}
                </p>
                <p className="sh-heading-lg text-primary-foreground">
                  {t("heroOverlayValue")}
                </p>
              </div>
              <div className="sh-badge-opaque absolute top-[12%] right-[8%] rounded-md px-3 py-2 sm:hidden">
                <p className="sh-micro uppercase tracking-wider text-on-dark-faint">
                  {t("heroOverlayLabel")}
                </p>
                <p className="sh-caption text-primary-foreground">
                  {t("heroOverlayValue")}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="hero-scroll absolute bottom-8 left-1/2 -translate-x-1/2" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M10 4v12m0 0l-4-4m4 4l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-on-dark-mute" />
        </svg>
      </div>

      <div className="h-20 md:h-28 bg-gradient-to-b from-primary-deep via-primary-deep/50 to-transparent" aria-hidden="true" />
    </section>
  )
}
```

- [ ] **Step 3: Verify hero section compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/landing/hero-section.tsx frontend/src/components/landing/skeleton-pose.tsx
git commit -m "feat(frontend): rewrite hero with next/image, GSAP targets, mobile image, gradient bridge"
```

---

### Task 7: How It Works Section (Features Rename)

**Files:**
- Modify: `frontend/src/components/landing/features-section.tsx`

- [ ] **Step 1: Rename and update features-section.tsx**

Update the component to use new i18n keys, add `id="how-it-works"`, add `tabindex="-1"`, change `md:grid-cols` to `lg:grid-cols`, add `.hiw-step` class for GSAP targeting, update watermark opacity:

```tsx
"use client"

import { Video, BarChart3, GitCompareArrows } from "lucide-react"
import { useTranslations } from "@/i18n"

const icons = [Video, BarChart3, GitCompareArrows]

export function HowItWorksSection() {
  const t = useTranslations("landing")

  const steps = [
    {
      title: t("howItWorksStep1Title"),
      description: t("howItWorksStep1Desc"),
      accent: t("howItWorksStep1Accent"),
    },
    {
      title: t("howItWorksStep2Title"),
      description: t("howItWorksStep2Desc"),
      accent: t("howItWorksStep2Accent"),
    },
    {
      title: t("howItWorksStep3Title"),
      description: t("howItWorksStep3Desc"),
      accent: t("howItWorksStep3Accent"),
    },
  ]

  const FirstIcon = icons[0]

  return (
    <section id="how-it-works" tabIndex={-1} className="relative mx-auto max-w-5xl px-6 py-20 md:py-28" aria-label={t("howItWorksTitle")}>
      <div className="mb-14 md:mb-20">
        <p className="mb-4 text-xs font-medium uppercase tracking-[0.3em] text-ink-mute">
          {t("howItWorksTitle")}
        </p>
        <h2 className="sh-display-xl text-ink max-w-xl">
          {t("howItWorksHeadline")}
        </h2>
      </div>

      <div className="hiw-step group relative mb-8 overflow-hidden rounded-lg border border-hairline bg-background p-8 lg:p-12">
        <span className="step-watermark">01</span>
        <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-10">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
            <FirstIcon className="h-6 w-6 text-primary group-hover:text-primary-foreground" />
          </div>
          <div>
            <h3 className="sh-display-md mb-3 text-ink">{steps[0].title}</h3>
            <p className="sh-body-md max-w-lg text-ink-mute">{steps[0].description}</p>
            <p className="mt-4 sh-caption font-medium text-primary">{steps[0].accent}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        {steps.slice(1).map((step, i) => {
          const Icon = icons[i + 1]
          return (
            <div
              key={step.title}
              className="hiw-step group relative overflow-hidden rounded-lg border border-hairline bg-background p-8"
            >
              <span className="step-watermark">{String(i + 2).padStart(2, "0")}</span>
              <div className="relative z-10">
                <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                  <Icon className="h-5 w-5 text-primary group-hover:text-primary-foreground" />
                </div>
                <h3 className="sh-heading-lg mb-2 text-ink">{step.title}</h3>
                <p className="sh-caption text-ink-mute">{step.description}</p>
                <p className="mt-3 sh-caption font-medium text-primary">{step.accent}</p>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/features-section.tsx
git commit -m "feat(frontend): rename Features to How It Works, update i18n keys, GSAP targets, lg: breakpoint"
```

---

### Task 8: Sticky Header

**Files:**
- Create: `frontend/src/components/landing/sticky-header.tsx`

- [ ] **Step 1: Create StickyHeader component**

Create `frontend/src/components/landing/sticky-header.tsx`:

```tsx
"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { useTranslations } from "@/i18n"
import { useAuth } from "@/components/auth-provider"
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
  const { isAuthenticated } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const hamburgerRef = useRef<HTMLButtonElement>(null)

  const closeMenu = useCallback(() => {
    setMenuOpen(false)
  }, [])

  const handleNavClick = useCallback((href: string) => {
    closeMenu()
    const el = document.querySelector(href)
    if (el) {
      el.scrollIntoView({ behavior: "smooth" })
      el.focus({ preventScroll: true })
    }
  }, [closeMenu])

  useEffect(() => {
    if (menuOpen) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => { document.body.style.overflow = "" }
  }, [menuOpen])

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeMenu()
    }
    if (menuOpen) window.addEventListener("keydown", onEsc)
    return () => window.removeEventListener("keydown", onEsc)
  }, [menuOpen, closeMenu])

  return (
    <header
      role="banner"
      className="fixed top-0 left-0 right-0 z-50 pt-[env(safe-area-inset-top)]"
      style={{ backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
    >
      <div className="header-bg absolute inset-0 bg-background opacity-0" />
      <div className="header-border absolute bottom-0 left-0 right-0 h-px border-b border-hairline opacity-0" />
      <div className="relative mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
        <a href="/" className="sh-display-md text-ink">
          SkateLab
        </a>

        <nav aria-label="Основная навигация" className="hidden md:flex items-center gap-8">
          {NAV_ITEMS.map((item) => (
            <button
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
            <a href={isAuthenticated ? "/feed" : "/register"}>
              {t("headerCta")}
            </a>
          </Button>
          <button
            ref={hamburgerRef}
            onClick={() => setMenuOpen(true)}
            className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="Открыть меню"
            aria-expanded={menuOpen}
          >
            <Menu className="h-6 w-6 text-ink" />
          </button>
        </div>
      </div>

      {/* Mobile menu overlay */}
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
                <span className="sh-display-md text-ink">SkateLab</span>
                <button
                  onClick={closeMenu}
                  className="min-h-[44px] min-w-[44px] flex items-center justify-center"
                  aria-label="Закрыть меню"
                >
                  <X className="h-6 w-6 text-ink" />
                </button>
              </div>
              <nav aria-label="Мобильная навигация" className="flex flex-col">
                {NAV_ITEMS.map((item) => (
                  <button
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/sticky-header.tsx
git commit -m "feat(frontend): add sticky header with hamburger menu and focus trap"
```

---

### Task 9: Trust Section (Animated Counters)

**Files:**
- Create: `frontend/src/components/landing/trust-section.tsx`

- [ ] **Step 1: Create TrustSection**

Create `frontend/src/components/landing/trust-section.tsx`:

```tsx
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/trust-section.tsx
git commit -m "feat(frontend): add trust section with animated counters and a11y"
```

---

### Task 10: Demo Section Rewrite (3-Phase Pinned Scroll)

**Files:**
- Modify: `frontend/src/components/landing/demo-section.tsx`

- [ ] **Step 1: Rewrite demo-section.tsx with GSAP pinned scroll, matchMedia, keyboard nav, mobile static cards**

```tsx
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
      if (!containerRef.current || !phase1OverlayRef.current || !skeletonRef.current || !badgesRef.current) return

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
          onUpdate: (self) => {
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
      setActivePhase((p) => Math.min(p + 1, 2))
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault()
      setActivePhase((p) => Math.max(p - 1, 0))
    }
  }, [])

  const isDesktop = typeof window !== "undefined" && window.innerWidth >= 1024
  const showPinned = isDesktop && !window.matchMedia("(prefers-reduced-motion: reduce)").matches

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
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.3em] text-ink-mute">
            {t("demoEyebrow")}
          </p>
          <h2 className="sh-display-xl text-ink">{t("demoHeadline")}</h2>
        </div>

        {/* Desktop: pinned container */}
        <div ref={containerRef} className="hidden lg:block relative mx-auto max-w-4xl overflow-hidden rounded-lg border border-hairline">
          <div className="relative aspect-video">
            <Image
              src="/images/demo-skater.webp"
              alt="Figure skater during a jump, with AI skeleton overlay tracking body position"
              width={1200}
              height={675}
              loading="lazy"
              className="h-full w-full object-cover"
            />

            {/* Phase 1 overlay — fades out in phase 2 */}
            <div ref={phase1OverlayRef} className="absolute inset-0 sh-demo-overlay" />
            <div className="absolute inset-0 sh-demo-glow" />

            {/* Phase 2: skeleton */}
            <div ref={skeletonRef}>
              <SkeletonPose role="img" aria-label="AI отслеживает 17 ключевых точек тела" />
            </div>

            {/* Phase 3: metric badges */}
            <div ref={badgesRef}>
              <div className="absolute top-[12%] left-[8%]">
                <div className="sh-badge-opaque rounded-md px-4 py-3 sh-metric-pulse">
                  <p className="sh-micro uppercase tracking-wider text-on-dark-faint">{t("demoMetricCoM")}</p>
                  <p className="sh-heading-lg text-primary-foreground tabular-nums">1.24 м</p>
                </div>
              </div>
              <div className="absolute right-[10%] bottom-[18%]">
                <div className="sh-badge-opaque rounded-md px-4 py-3 sh-metric-pulse">
                  <p className="sh-micro uppercase tracking-wider text-on-dark-faint">{t("demoMetricRotation")}</p>
                  <p className="sh-heading-lg text-primary-foreground tabular-nums">540°</p>
                </div>
              </div>
              <div className="absolute top-[45%] right-[6%]">
                <div className="sh-badge-opaque rounded-md px-4 py-3 sh-metric-pulse">
                  <p className="sh-micro uppercase tracking-wider text-on-dark-faint">{t("demoMetricAirtime")}</p>
                  <p className="sh-heading-lg text-primary-foreground tabular-nums">0.72 с</p>
                </div>
              </div>
              <div className="sh-badge-opaque absolute bottom-4 left-4 right-4 flex items-center justify-between rounded-sm px-4 py-2">
                <p className="sh-micro text-on-dark-mute">{t("demoSpecPoints")}</p>
                <p className="sh-micro text-on-dark-faint">{t("demoSpecFps")}</p>
              </div>
            </div>
          </div>

          {/* Phase navigation (keyboard) */}
          <div
            className="flex items-center justify-center gap-4 py-4"
            role="radiogroup"
            aria-label="Фазы демо"
            onKeyDown={handleKeyDown}
          >
            {PHASES.map((key, i) => (
              <button
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

        {/* Mobile/tablet: 3 static phase cards */}
        <div className="grid gap-4 lg:hidden">
          {PHASES.map((key, i) => (
            <div key={key} className="rounded-lg border border-hairline overflow-hidden">
              <div className="relative aspect-video">
                <Image
                  src="/images/demo-skater.webp"
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
                        <p className="sh-micro uppercase tracking-wider text-on-dark-faint">{t("demoMetricCoM")}</p>
                        <p className="text-sm font-semibold text-white">1.24 м</p>
                      </div>
                    </div>
                    <div className="absolute right-[10%] bottom-[18%]">
                      <div className="sh-badge-opaque rounded-md px-3 py-2">
                        <p className="sh-micro uppercase tracking-wider text-on-dark-faint">{t("demoMetricRotation")}</p>
                        <p className="text-sm font-semibold text-white">540°</p>
                      </div>
                    </div>
                    <div className="absolute top-[45%] right-[6%]">
                      <div className="sh-badge-opaque rounded-md px-3 py-2">
                        <p className="sh-micro uppercase tracking-wider text-on-dark-faint">{t("demoMetricAirtime")}</p>
                        <p className="text-sm font-semibold text-white">0.72 с</p>
                      </div>
                    </div>
                  </>
                )}
              </div>
              <p className="px-4 py-3 sh-caption font-medium text-ink">{t(key)}</p>
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/demo-section.tsx
git commit -m "feat(frontend): rewrite demo section with 3-phase pinned scroll, keyboard nav, mobile cards"
```

---

### Task 11: Pricing Section

**Files:**
- Create: `frontend/src/components/landing/pricing-section.tsx`

- [ ] **Step 1: Create PricingSection**

Create `frontend/src/components/landing/pricing-section.tsx`:

```tsx
"use client"

import { useTranslations } from "@/i18n"
import { Button } from "@/components/ui/button"
import { Check } from "lucide-react"

export function PricingSection() {
  const t = useTranslations("landing")

  const tiers = [
    {
      name: t("pricingFreeName"),
      price: t("pricingFreePrice"),
      desc: t("pricingFreeDesc"),
      features: t("pricingFreeFeatures").split("|"),
      cta: t("pricingFreeCta"),
      href: "/register",
      highlighted: false,
    },
    {
      name: t("pricingProName"),
      price: t("pricingProPrice"),
      desc: t("pricingProDesc"),
      features: t("pricingProFeatures").split("|"),
      cta: t("pricingProCta"),
      href: "https://t.me/SkateLabPro",
      highlighted: true,
      badge: t("pricingProBadge"),
    },
    {
      name: t("pricingCoachName"),
      price: t("pricingCoachPrice"),
      desc: t("pricingCoachDesc"),
      features: t("pricingCoachFeatures").split("|"),
      cta: t("pricingCoachCta"),
      href: "https://t.me/SkateLabBot",
      highlighted: false,
    },
  ]

  return (
    <section
      id="pricing"
      tabIndex={-1}
      className="border-t border-hairline mx-auto max-w-5xl px-6 py-20 md:py-28"
      aria-labelledby="pricing-heading"
    >
      <div className="mb-14 md:mb-20 text-center">
        <p className="mb-4 text-xs font-medium uppercase tracking-[0.3em] text-ink-mute">
          {t("pricingTitle")}
        </p>
        <h2 id="pricing-heading" className="sh-display-xl text-ink">
          {t("pricingTitle")}
        </h2>
      </div>

      <ul className="grid gap-8 lg:grid-cols-3" role="list">
        {tiers.map((tier) => (
          <li
            key={tier.name}
            className={`pricing-card relative rounded-lg border p-8 ${
              tier.highlighted
                ? "ring-2 ring-primary shadow-sm shadow-surface-violet-soft/20"
                : "border-hairline bg-background"
            }`}
          >
            {tier.badge && (
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 sh-badge-opaque px-3 py-1 rounded-full text-xs text-primary-foreground">
                {tier.badge}
              </span>
            )}
            <h3 className="sh-heading-lg text-ink">{tier.name}</h3>
            <p className="sh-price mt-4 text-ink">
              <data value={tier.price.replace(/[^\d]/g, "")}>{tier.price}</data>
            </p>
            <p className="mt-2 sh-caption text-ink-mute">{tier.desc}</p>
            <ul className="mt-6 space-y-3">
              {tier.features.map((f) => (
                <li key={f} className="flex items-start gap-2 sh-caption text-ink-mute">
                  <Check className="h-4 w-4 mt-0.5 shrink-0 text-score-good" />
                  {f}
                </li>
              ))}
            </ul>
            <Button
              variant={tier.highlighted ? "default" : "outline"}
              className="mt-6 min-h-[44px] w-full"
              asChild
            >
              <a
                href={tier.href}
                {...(tier.href.startsWith("http") ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              >
                {tier.cta}
              </a>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/pricing-section.tsx
git commit -m "feat(frontend): add pricing section with 3 tiers, Pro highlight, Telegram CTAs"
```

---

### Task 12: FAQ Section

**Files:**
- Create: `frontend/src/components/landing/faq-section.tsx`

- [ ] **Step 1: Create FAQSection**

Create `frontend/src/components/landing/faq-section.tsx`:

```tsx
"use client"

import { useTranslations } from "@/i18n"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"

const FAQ_KEYS = [1, 2, 3, 4, 5, 6, 7] as const

export function FAQSection() {
  const t = useTranslations("landing")

  return (
    <section
      id="faq"
      tabIndex={-1}
      className="border-t border-hairline mx-auto max-w-3xl px-6 py-20 md:py-28"
      aria-labelledby="faq-heading"
    >
      <div className="faq-header mb-10">
        <p className="mb-4 text-xs font-medium uppercase tracking-[0.3em] text-ink-mute">
          {t("faqTitle")}
        </p>
        <h2 id="faq-heading" className="sh-display-xl text-ink">
          {t("faqTitle")}
        </h2>
      </div>

      <Accordion type="single" collapsible>
        {FAQ_KEYS.map((n) => (
          <AccordionItem key={n} value={`faq-${n}`}>
            <AccordionTrigger className="min-h-[44px] py-3 text-left">
              {t(`faqQ${n}`)}
            </AccordionTrigger>
            <AccordionContent className="sh-body-md text-ink-mute">
              {t(`faqA${n}`)}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </section>
  )
}
```

- [ ] **Step 2: Verify shadcn Accordion component exists**

Run: `ls frontend/src/components/ui/accordion.tsx 2>/dev/null && echo "EXISTS" || echo "MISSING"`

If missing, run: `cd frontend && bunx shadcn@latest add accordion`

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/landing/faq-section.tsx
git commit -m "feat(frontend): add FAQ section with shadcn accordion"
```

---

### Task 13: CTA Section Update

**Files:**
- Modify: `frontend/src/components/landing/cta-section.tsx`

- [ ] **Step 1: Rewrite CTA section with updated copy**

```tsx
"use client"

import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { useAuth } from "@/components/auth-provider"

export function CTASection() {
  const t = useTranslations("landing")
  const { isAuthenticated } = useAuth()

  return (
    <section className="cta-section sh-teal-band" aria-labelledby="cta-heading">
      <div className="relative mx-auto max-w-5xl px-6 py-24 md:py-32">
        <div className="max-w-lg">
          <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-on-dark-mute">
            {t("ctaEyebrow")}
          </p>
          <h2 id="cta-heading" className="sh-display-lg text-primary-foreground">
            {t("ctaHeadlineNew")}
          </h2>
          <p className="mt-4 sh-body-lg text-on-dark-mute">
            {t("ctaSubtitleNew")}
          </p>
          <div className="mt-10 flex flex-col items-start gap-4 sm:flex-row">
            <Button
              variant="on-teal"
              size="lg"
              className="min-h-[44px] px-10 text-base"
              asChild
            >
              <a href={isAuthenticated ? "/feed" : "/register"}>
                {t("ctaPrimary")}
              </a>
            </Button>
            {!isAuthenticated && (
              <a
                href="/login"
                className="min-h-[44px] flex items-center sh-body-md text-on-dark-mute underline hover:text-primary-foreground"
              >
                {t("ctaHasAccount")}
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/cta-section.tsx
git commit -m "feat(frontend): update CTA section with new copy and ghost login link"
```

---

### Task 14: Footer Section

**Files:**
- Create: `frontend/src/components/landing/footer-section.tsx`

- [ ] **Step 1: Create FooterSection**

Create `frontend/src/components/landing/footer-section.tsx`:

```tsx
"use client"

import { useTranslations } from "@/i18n"

export function FooterSection() {
  const t = useTranslations("landing")

  return (
    <footer role="contentinfo" className="border-t border-hairline bg-background">
      <div className="mx-auto max-w-5xl px-6 py-12 md:py-16">
        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
          {/* Brand */}
          <div>
            <p className="sh-display-md text-ink">SkateLab</p>
            <p className="sh-caption text-ink-mute mt-1">{t("footerTagline")}</p>
            <a
              href="/register"
              className="sh-button-cap text-link hover:underline mt-2 inline-block min-h-[44px] flex items-center"
            >
              {t("ctaPrimary")} →
            </a>
          </div>

          {/* Product */}
          <nav aria-label={t("footerProduct")}>
            <p className="sh-button-cap text-ink-mute mb-3">{t("footerProduct")}</p>
            <ul className="space-y-2">
              <li>
                <a href="#how-it-works" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerHowItWorks")}
                </a>
              </li>
              <li>
                <a href="#pricing" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerPricing")}
                </a>
              </li>
              <li>
                <a href="#faq" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerFaq")}
                </a>
              </li>
            </ul>
          </nav>

          {/* Legal */}
          <nav aria-label={t("footerLegal")}>
            <p className="sh-button-cap text-ink-mute mb-3">{t("footerLegal")}</p>
            <ul className="space-y-2">
              <li>
                <a href="/privacy" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerPrivacy")}
                </a>
              </li>
              <li>
                <a href="/terms" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerTerms")}
                </a>
              </li>
              <li>
                <a href="/offer" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerOffer")}
                </a>
              </li>
              <li>
                <a href="/cookies" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerCookiePolicy")}
                </a>
              </li>
            </ul>
          </nav>

          {/* Contact */}
          <div aria-label={t("footerContact")}>
            <p className="sh-button-cap text-ink-mute mb-3">{t("footerContact")}</p>
            <ul className="space-y-2">
              <li>
                <a
                  href="https://t.me/SkateLabBot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  Telegram
                </a>
              </li>
              <li>
                <a
                  href="https://vk.com/skatelab"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  VK
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-8 border-t border-hairline pt-6">
          <p className="sh-legal text-ink-mute">{t("footerCopyright")}</p>
        </div>
      </div>
    </footer>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/footer-section.tsx
git commit -m "feat(frontend): add footer with brand, product, legal, contact columns"
```

---

### Task 15: Cookie Banner

**Files:**
- Create: `frontend/src/components/landing/cookie-banner.tsx`

- [ ] **Step 1: Create CookieBanner**

Create `frontend/src/components/landing/cookie-banner.tsx`:

```tsx
"use client"

import { useTranslations } from "@/i18n"
import { Button } from "@/components/ui/button"
import FocusLock from "react-focus-lock"

interface CookieBannerProps {
  onAccept: () => void
}

export default function CookieBanner({ onAccept }: CookieBannerProps) {
  const t = useTranslations("landing")

  return (
    <FocusLock returnFocus>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cookie-heading"
        className="fixed bottom-0 left-0 right-0 z-[70] border-t border-hairline bg-canvas-soft shadow-lg shadow-primary/5 pb-[env(safe-area-inset-bottom)]"
      >
        <div className="mx-auto max-w-5xl px-6 py-4">
          <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 id="cookie-heading" className="sr-only">{t("cookieHeading")}</h2>
              <p className="sh-body-md text-ink-mute">
                {t("cookieText")}{" "}
                <a href="/cookies" className="text-link hover:underline">
                  Cookie Policy
                </a>
              </p>
            </div>
            <Button
              onClick={onAccept}
              autoFocus
              className="min-h-[44px] min-w-[120px] shrink-0"
            >
              {t("cookieAccept")}
            </Button>
          </div>
        </div>
      </div>
    </FocusLock>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/cookie-banner.tsx
git commit -m "feat(frontend): add cookie banner with focus trap and SSR safety"
```

---

### Task 16: Mobile CTA Bar

**Files:**
- Create: `frontend/src/components/landing/mobile-cta-bar.tsx`

- [ ] **Step 1: Create MobileCTABar**

Create `frontend/src/components/landing/mobile-cta-bar.tsx`:

```tsx
"use client"

import { useTranslations } from "@/i18n"
import { Button } from "@/components/ui/button"

interface MobileCTABarProps {
  hidden: boolean
}

export function MobileCTABar({ hidden }: MobileCTABarProps) {
  const t = useTranslations("landing")

  if (hidden) return null

  return (
    <div
      role="complementary"
      aria-label={t("ctaPrimary")}
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-hairline bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <div className="flex items-center justify-center px-4 py-3">
        <Button
          size="lg"
          className="min-h-[44px] w-full max-w-md"
          asChild
        >
          <a href="/register">{t("ctaPrimary")}</a>
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/mobile-cta-bar.tsx
git commit -m "feat(frontend): add mobile CTA bar with cookie banner conflict handling"
```

---

### Task 17: Legal Pages

**Files:**
- Create: `frontend/src/app/(landing)/legal-layout.tsx`
- Create: `frontend/src/app/(landing)/privacy/page.tsx`
- Create: `frontend/src/app/(landing)/terms/page.tsx`
- Create: `frontend/src/app/(landing)/offer/page.tsx`
- Create: `frontend/src/app/(landing)/cookies/page.tsx`

- [ ] **Step 1: Create shared legal layout**

Create `frontend/src/app/(landing)/legal-layout.tsx`:

```tsx
import Link from "next/link"

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-hairline px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <Link href="/" className="sh-display-md text-ink">
            SkateLab
          </Link>
          <Link href="/" className="sh-caption text-link hover:underline">
            На главную
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">
        {children}
      </main>
    </div>
  )
}
```

- [ ] **Step 2: Create Privacy Policy page (real content)**

Create `frontend/src/app/(landing)/privacy/page.tsx`:

```tsx
import type { Metadata } from "next"
import LegalLayout from "../legal-layout"

export const metadata: Metadata = {
  title: "Политика конфиденциальности — SkateLab",
}

export default function PrivacyPage() {
  return (
    <LegalLayout>
      <nav className="mb-6 sh-caption text-ink-mute">
        <a href="/" className="hover:text-ink">Главная</a>
        {" > "}
        <span>Правовая информация</span>
        {" > "}
        <span>Политика конфиденциальности</span>
      </nav>
      <h1 className="sh-display-lg text-ink mb-8">Политика конфиденциальности</h1>

      <div className="prose prose-neutral max-w-none sh-body-md text-ink-mute space-y-6">
        <h2 className="sh-heading-lg text-ink">1. Общие положения</h2>
        <p>Настоящая Политика конфиденциальности (далее — Политика) определяет порядок обработки и защиты персональных данных пользователей сервиса SkateLab (далее — Сервис), принадлежащего ООО «СкейтЛаб» (далее — Оператор).</p>

        <h2 className="sh-heading-lg text-ink">2. Состав персональных данных</h2>
        <p>Оператор обрабатывает следующие персональные данные пользователя: имя, адрес электронной почты, видео- и биометрические данные (скелетон тела), загруженные пользователем для анализа.</p>

        <h2 className="sh-heading-lg text-ink">3. Цели обработки</h2>
        <p>Персональные данные обрабатываются в целях: предоставления сервиса биомеханического анализа видео; идентификации пользователя; связи с пользователем; улучшения качества сервиса.</p>

        <h2 className="sh-heading-lg text-ink">4. Правовые основания</h2>
        <p>Обработка персональных данных осуществляется на основании согласия субъекта персональных данных (ст. 6 п. 1 пп. 1 ФЗ-152) и исполнения договора (ст. 6 п. 1 пп. 5 ФЗ-152).</p>

        <h2 className="sh-heading-lg text-ink">5. Биометрические данные</h2>
        <p>Обработка биометрических данных (скелетон тела, полученный из видео) осуществляется только с отдельного согласия пользователя. Биометрические данные обрабатываются в анонимизированном виде. Согласие запрашивается при первой загрузке видео.</p>

        <h2 className="sh-heading-lg text-ink">6. Хранение и защита</h2>
        <p>Персональные данные хранятся в зашифрованном виде. Срок хранения — до удаления аккаунта пользователем или до истечения срока, установленного законодательством. Оператор принимает организационные и технические меры для защиты данных от несанкционированного доступа.</p>

        <h2 className="sh-heading-lg text-ink">7. Права субъекта</h2>
        <p>Пользователь вправе: запросить информацию об обработке своих данных; потребовать уточнения, блокирования или удаления данных; отозвать согласие на обработку.</p>

        <h2 className="sh-heading-lg text-ink">8. Контакт</h2>
        <p>По вопросам обработки персональных данных обращайтесь: <a href="https://t.me/SkateLabBot" className="text-link">Telegram</a></p>
      </div>
    </LegalLayout>
  )
}
```

- [ ] **Step 3: Create Terms stub**

Create `frontend/src/app/(landing)/terms/page.tsx`:

```tsx
import type { Metadata } from "next"
import Link from "next/link"
import LegalLayout from "../legal-layout"

export const metadata: Metadata = {
  title: "Пользовательское соглашение — SkateLab",
}

export default function TermsPage() {
  return (
    <LegalLayout>
      <nav className="mb-6 sh-caption text-ink-mute">
        <a href="/" className="hover:text-ink">Главная</a>
        {" > "}
        <span>Правовая информация</span>
        {" > "}
        <span>Пользовательское соглашение</span>
      </nav>
      <h1 className="sh-display-lg text-ink mb-8">Пользовательское соглашение</h1>
      <p className="sh-body-lg text-ink-mute">Документ готовится.</p>
      <p className="mt-4">
        <Link href="/" className="sh-button-cap text-link hover:underline">На главную →</Link>
      </p>
    </LegalLayout>
  )
}
```

- [ ] **Step 4: Create Offer stub**

Create `frontend/src/app/(landing)/offer/page.tsx`:

```tsx
import type { Metadata } from "next"
import Link from "next/link"
import LegalLayout from "../legal-layout"

export const metadata: Metadata = {
  title: "Оферта — SkateLab",
}

export default function OfferPage() {
  return (
    <LegalLayout>
      <nav className="mb-6 sh-caption text-ink-mute">
        <a href="/" className="hover:text-ink">Главная</a>
        {" > "}
        <span>Правовая информация</span>
        {" > "}
        <span>Оферта</span>
      </nav>
      <h1 className="sh-display-lg text-ink mb-8">Оферта</h1>
      <p className="sh-body-lg text-ink-mute">Документ готовится.</p>
      <p className="mt-4">
        <Link href="/" className="sh-button-cap text-link hover:underline">На главную →</Link>
      </p>
    </LegalLayout>
  )
}
```

- [ ] **Step 5: Create Cookie Policy page (real content)**

Create `frontend/src/app/(landing)/cookies/page.tsx`:

```tsx
import type { Metadata } from "next"
import LegalLayout from "../legal-layout"

export const metadata: Metadata = {
  title: "Cookie Policy — SkateLab",
}

export default function CookiesPage() {
  return (
    <LegalLayout>
      <nav className="mb-6 sh-caption text-ink-mute">
        <a href="/" className="hover:text-ink">Главная</a>
        {" > "}
        <span>Правовая информация</span>
        {" > "}
        <span>Cookie Policy</span>
      </nav>
      <h1 className="sh-display-lg text-ink mb-8">Cookie Policy</h1>

      <div className="prose prose-neutral max-w-none sh-body-md text-ink-mute space-y-6">
        <h2 className="sh-heading-lg text-ink">Что такое cookies</h2>
        <p>Cookies — небольшие текстовые файлы, которые хранятся на вашем устройстве при посещении сайта.</p>

        <h2 className="sh-heading-lg text-ink">Какие cookies мы используем</h2>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-hairline">
              <th className="py-2 pr-4 sh-button-cap text-ink">Cookie</th>
              <th className="py-2 pr-4 sh-button-cap text-ink">Категория</th>
              <th className="py-2 pr-4 sh-button-cap text-ink">Назначение</th>
              <th className="py-2 sh-button-cap text-ink">Срок</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-hairline">
              <td className="py-2 pr-4"><code>sb_auth</code></td>
              <td className="py-2 pr-4">Необходимые</td>
              <td className="py-2 pr-4">Идентификация авторизованного пользователя</td>
              <td className="py-2">Сессия</td>
            </tr>
            <tr className="border-b border-hairline">
              <td className="py-2 pr-4"><code>consent_accepted</code></td>
              <td className="py-2 pr-4">Необходимые</td>
              <td className="py-2 pr-4">Хранение согласия на использование cookies</td>
              <td className="py-2">1 год</td>
            </tr>
          </tbody>
        </table>

        <h2 className="sh-heading-lg text-ink">Аналитические cookies</h2>
        <p>В настоящий момент мы не используем аналитические cookies. При внедрении (PostHog) они будут требовать вашего согласия и использовать анонимизированные идентификаторы. Срок хранения — не более 13 месяцев.</p>

        <h2 className="sh-heading-lg text-ink">Управление cookies</h2>
        <p>Вы можете отключить cookies в настройках браузера. Это может ограничить функциональность сервиса.</p>
      </div>
    </LegalLayout>
  )
}
```

- [ ] **Step 6: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/\(landing\)/legal-layout.tsx frontend/src/app/\(landing\)/privacy/ frontend/src/app/\(landing\)/terms/ frontend/src/app/\(landing\)/offer/ frontend/src/app/\(landing\)/cookies/
git commit -m "feat(frontend): add legal pages (privacy, terms stub, offer stub, cookie policy)"
```

---

### Task 18: Add Viewport Export to Root Layout

**Files:**
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Add viewport export**

Add before `generateMetadata`:

```tsx
import type { Viewport } from "next"

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
}
```

Also update `<html>` to remove `suppressHydrationWarning` if only needed for next-themes. Keep it since the root layout still has ThemeProvider for `(auth)` and `(app)` route groups.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/layout.tsx
git commit -m "feat(frontend): add viewport export with viewport-fit cover for safe area"
```

---

### Task 19: Full Build Verification

- [ ] **Step 1: Run TypeScript check**

Run: `cd frontend && bunx tsc --noEmit`

Fix any type errors found.

- [ ] **Step 2: Run linter**

Run: `cd frontend && bunx next lint`

Fix any lint errors found.

- [ ] **Step 3: Run dev server and verify visually**

Run: `cd frontend && bun run dev`

Open `http://localhost:3000` and verify:
- Landing page loads (not blank)
- Hero section renders with image
- Sticky header appears
- Sections scroll smoothly
- Cookie banner shows on first visit
- Mobile responsive layout works

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "fix(frontend): resolve build and type errors from landing redesign"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Section | Task |
|---|---|
| Sticky Header | Task 8 |
| Hero Section | Task 6 |
| How It Works | Task 7 |
| Trust Wall | Task 9 |
| Demo Section | Task 10 |
| Pricing | Task 11 |
| FAQ | Task 12 |
| CTA Section | Task 13 |
| Footer | Task 14 |
| Cookie Banner | Task 15 |
| Legal Pages | Task 17 |
| Mobile CTA Bar | Task 16 |
| Route Group + Auth Redirect | Task 2 |
| CSS/Token Amendments | Task 3 |
| i18n Migration | Task 4 |
| GSAP Orchestrator | Task 5 |
| Viewport Export | Task 18 |
| Dependencies | Task 1 |
| SEO/JSON-LD | Task 2 (page.tsx) |

### 2. Placeholder Scan

No TBD, TODO, or "implement later" found. All code is complete.

### 3. Type Consistency

- `SkeletonPoseProps` interface matches usage across hero and demo
- `CookieBannerProps.onAccept: () => void` matches `acceptCookies` in LandingClient
- `MobileCTABarProps.hidden: boolean` matches `showCookieBanner` in LandingClient
- i18n key names consistent between JSON files and component usage
