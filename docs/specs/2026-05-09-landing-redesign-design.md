# Landing Page Redesign — Design Spec

> Date: 2026-05-09
> Status: Approved
> Scope: Full landing page redesign with GSAP scroll animations, new sections, legal stubs

## Context

Current landing has 4 sections (Hero, Features, Demo, CTA). Missing: footer, navigation, testimonials, pricing, FAQ, trust indicators, legal compliance. Animations are CSS-only (fade-up, pulse). Images are Unsplash placeholders without next/image. No scroll-triggered motion.

Product positioning (from CustDev): coaches buy time savings + fewer disputes. Skaters buy faster progress. Key insight: "Измеряй технику, а не угадывай."

## Design Principles

- **Register:** Product (design serves the product, not IS the product)
- **3-canvas system:** indigo navy hero → gradient transition → white canvas body → deep teal closing CTA. No hard edges between canvases.
- **Brand voice:** точный, спортивный, уверенный. Direct, no fluff. Russian-first.
- **Anti-references:** generic SaaS cream, crypto neon, health-tech softness, winter clichés
- **Color strategy:** Restrained with one accent (surface-violet-soft ≤10% on hero, surface-teal-deep on CTA). On dark backgrounds: violet-soft works. On white backgrounds: use `--primary` (dark indigo) instead — violet-soft fails WCAG on white (1.64:1).
- **Motion strategy:** Superhuman-level — GSAP ScrollTrigger for entrances, parallax, pinned demo. No WebGL shaders. Single timing system (stagger 0.12s, ease power2.out, durations from token scale).
- **Dark mode:** Disabled on landing page. Force light theme regardless of system preference. The 3-canvas narrative breaks in dark mode.
- **Content widths:** Two standard widths: `max-w-5xl` (1024px) for layout sections, `max-w-3xl` (768px) for reading sections. Replace all ad-hoc values.

## Section Architecture (top → bottom)

### 1. Sticky Header

**Structure:** Fixed top bar. Transparent on hero → white with backdrop-blur on scroll.

**Elements:**
- Left: SkateLab wordmark (text, not logo image)
- Center: Nav links — Как это работает / Тарифы / FAQ (smooth-scroll to anchors)
- Right: CTA button «Начать бесплатно» (links to /register), or avatar+name if authenticated

**HTML:** `<header role="banner">`. Nav links in `<nav aria-label="Основная навигация">`. Skip-to-content link as first focusable element → `#main-content`.

**GSAP:** Static backdrop-blur (always applied, not animated). Animate only `opacity` of a white background overlay: 0 on hero → 1 after scroll past hero. Animate `border-bottom` opacity (0 → 1). Do NOT animate `backdrop-filter` (performance hazard).

**Mobile:** Hamburger menu. Slide-in panel from right. CTA stays visible. Touch targets min 44x44px.

**Safe area:** `top: env(safe-area-inset-top)` for iPhone notch/Dynamic Island.

**Focus management:** Smooth-scroll anchors move focus to target section via `element.focus()` with `tabindex="-1"`.

**Auth redirect:** If `sb_auth` cookie present, server-side redirect `/` → `/feed`. Landing is for new visitors only.

### 2. Hero Section

**Layout:** Full-viewport (`min-h-[100dvh]`). Grid: `grid-cols-1 lg:grid-cols-[1fr_1.1fr]` asymmetric split. On mobile/tablet (< 1024px): single column, text first, compact image second.

**Left column:**
- Eyebrow: `sh-micro uppercase tracking-[0.3em] text-on-dark-mute` — «AI Тренер по фигурному катанию»
- H1: `sh-display-xxl text-primary-foreground` — single `<h1>` with `<br>` and second line as `<span class="text-surface-violet-soft">`:
  ```
  <h1 class="sh-display-xxl">Запишите прыжок.<br><span class="text-surface-violet-soft">Увидьте миллиметры.</span></h1>
  ```
- Subtitle: `sh-body-lg text-on-dark-mute max-w-2xl` — CustDev-validated copy. `max-w-lg` yields only ~47ch (below 65-75ch optimal).
- Stat: inline `sh-display-lg font-bold text-surface-violet-soft` — «< 15 с» + label «на полный разбор видео»
- Dual CTA: Primary «Начать бесплатно» (on-dark-pill, min-h-[44px]), Secondary «Смотреть демо» (ghost, smooth-scroll to #demo). Changed from «Как это работает» — users want to see the product, not read explanation.

**Right column:**
- Stock photo of figure skater in jump with dark overlay + SVG skeleton overlay (SkeletonPose with `role="img" aria-label="AI отслеживает 17 ключевых точек тела"`) + opaque metric badge (Высота ЦМТ: 1.24 м)
- Desktop: `aspect-[4/5]`, `rounded-lg`, `overflow-hidden`
- Mobile/tablet: visible at `sm:` with shorter `aspect-[16/9]`. Not hidden entirely — mobile users need visual proof.
- `priority` prop (next/image), explicit `width`/`height` for CLS

**Mobile CTA visibility:** Reduce hero padding on mobile (`py-8 sm:py-16 lg:py-0`). Ensure CTA buttons visible above fold on 375x667 iPhone SE. Consider sticky mobile CTA bar (fixed bottom, `z-40`, `md:hidden`) with single «Начать бесплатно» button.

**Hero-to-body transition:** Add gradient fade zone (~80-120px) at hero bottom: `bg-gradient-to-b from-primary-deep via-primary-deep/50 to-transparent`. Prevents hard edge where dark hero meets white body.

**GSAP:** Staggered fade-up entrance with consistent 0.12s stagger (not irregular 0.2/0.3s gaps). Remove CSS hero animation classes — use GSAP for all motion.

### 3. How It Works (replaces Features)

**Layout:** `max-w-5xl`, white canvas background.

**Section opener:** Left-aligned eyebrow «Как это работает» + h2 `sh-display-xl` «Три шага от видео до рекомендаций» + `id="how-it-works" tabindex="-1"` for anchor navigation.

**3 steps:**
- Step 1 (dominant, full-width card): Upload video — accent: «Никаких специальных камер или настроек»
- Step 2 (paired left, wider): Get the breakdown — accent: «12+ параметров по каждому кадру»
- Step 3 (paired right, narrower): Compare to reference — accent: «Объективные данные для тренера и ученика»

**Structure:** Step 1 = `p-8 lg:p-12`, horizontal layout (icon + text). Steps 2-3 = `lg:grid-cols-[1.2fr_1fr]` (changed from md: — paired layout only on desktop). All steps stack vertically on mobile/tablet. Watermark numbers (01, 02, 03) with `overflow-hidden` on step containers to prevent horizontal overflow. Icon circles with instant color flip on hover (no transition under reduced-motion).

**Watermark visibility:** Raise watermark opacity from `0.15` to `0.25` with `oklch(0.7 0.006 80 / 0.25)`. Current 0.15 is invisible (1.05:1 CR).

**GSAP:** `ScrollTrigger` with `toggleActions: 'play none none none'`. Each step: `opacity: 0, y: 40 → opacity: 1, y: 0` with stagger 0.12s.

### 4. Demo Section (GSAP pinned scroll)

**KILLER FEATURE.** This is the product demo shown through scroll.

**Structure:**
- Container: `max-w-5xl`, `aspect-video`, centered. `id="demo" tabindex="-1"` for anchor navigation.
- Pin: `scrollTrigger: { pin: true, scrub: 1, end: '+=100%', anticipatePin: 1 }` (reduced from +=200% — 3 viewports pinned is too long).
- 3 phases scrubbed by scroll position (0-33%, 33-66%, 66-100%) — evenly distributed:
  1. **Raw video** — stock skating image, no overlay
  2. **Skeleton overlay** — same image + SkeletonPose + dark overlay
  3. **Metrics HUD** — skeleton + 3 opaque metric badges (Высота ЦМТ, Доворот, Время полёта) + tech spec strip

**Below pinned area:** Text «Видео → Скелетон → Метрики за 12 секунд» as a pipeline explanation.

**Keyboard accessibility:** Add phase navigation controls (3 radio-style dots or a stepper). Keyboard users cannot scrub — provide `ArrowRight`/`ArrowLeft` to advance/retreat phases, or clickable phase indicators that programmatically scroll to the phase position.

**Mobile/tablet (< 1024px):** No pin. Simple `whileInView` entrance animation via `gsap.matchMedia()`. 3 static phase cards stacked vertically (before/after style), each with the image at that phase. Pin breakpoint changed from 768px to 1024px — tablets should not get pinned scroll (poor UX with touch).

**Reduced-motion:** Under `prefers-reduced-motion: reduce`, show 3 static phase cards regardless of viewport width. Disable pin entirely. Add to GSAP matchMedia: `(min-width: 1024px) and (prefers-reduced-motion: no-preference)`.

**GSAP timeline:**
```
const mm = gsap.matchMedia()

mm.add("(min-width: 1024px) and (prefers-reduced-motion: no-preference)", () => {
  // Desktop: pinned 3-phase scroll, evenly distributed
  gsap.timeline({
    scrollTrigger: { trigger, pin: true, scrub: 1, end: '+=100%', anticipatePin: 1 }
  })
    .to(phase1Overlay, { opacity: 0, duration: 1 })       // 0 → 1
    .to(phase2Elements, { opacity: 1, duration: 1 }, 1)     // 1 → 2 (after phase 1)
    .to(phase3Badges, { opacity: 1, y: 0, duration: 1 }, 2) // 2 → 3 (after phase 2)
})

mm.add("(max-width: 1023px), (prefers-reduced-motion: reduce)", () => {
  // Mobile/tablet/reduced-motion: simple entrance, no pin
  gsap.from(demoContainer, { opacity: 0, y: 30, duration: 0.6,
    scrollTrigger: { trigger: demoContainer, start: 'top 85%', toggleActions: 'play none none none' }
  })
})
```

Use `dvh` units for viewport height (`min-h-[100dvh]`) to avoid mobile address bar issues.

**Back-navigation:** Add `ScrollTrigger.refresh()` on `pageshow` event to fix scroll restoration after browser back.

**Badge contrast:** Raise `sh-badge-opaque` opacity from 0.85 to 0.92-0.95 to guarantee text readability on bright ice backgrounds.

### 5. Trust Wall (Animated Counters)

**No placeholder testimonials.** Fake quotes damage credibility. Trust wall uses only animated counters until real testimonials available post-pilot.

**Animated counters:**
- «1,200+ сессий проанализировано»
- «340+ фигуристов»
- «15+ клубов»

**Section heading:** H2 `sh-display-xl text-ink` — «Нам доверяют» or sr-only heading if visually minimal design preferred.

**Layout:** `lg:grid-cols-3`, centered (changed from md: — 3 columns too tight on tablet). Each counter: large number (`sh-display-lg font-bold text-primary` — NOT violet-soft which fails WCAG on white at 1.64:1) + label (`sh-caption text-ink-mute`).

**GSAP:** Counter animation with proportional durations and easing: 1200 → 1.0s, 340 → 0.8s, 15 → 0.6s. All use `ease: "power2.out"`. Not a flat 2s for all values.

**Reduced motion:** Show final value immediately, no counting animation.

### 6. Pricing

**3 tiers** from unit-economics.md:

| Tier | Price | Segment | Included |
|------|-------|---------|----------|
| **Free** | 0 ₽/мес | Начинающие | 3 анализа/мес, базовый скелетон |
| **Pro** | 990 ₽/мес | Фигуристы | Безлимит анализов, рекомендации, прогресс, сравнение с эталоном |
| **Coach** | 3,500 ₽/мес | Тренеры | Dashboard учеников, диагностика, отчёты, до 20 учеников |

**Layout:** `lg:grid-cols-3`, centered (changed from md: — 3 columns too tight on tablet for Russian text). Pro card multi-signal highlight: `ring-2 ring-surface-violet-soft` + `shadow-sm shadow-surface-violet-soft/20` + «Популярный» text badge at top. Not just ring-2 ring-primary (too thin, indistinguishable). Each card: tier name, price, description, feature list (✓ check icons in `<ul>/<li>`), CTA button. Price uses `sh-price` class (`clamp(2.25rem, 4vw, 3rem), font-weight: 700, line-height: 1, letter-spacing: -0.03em`).

**CTA copy (unified):** Free → «Начать бесплатно» (same label everywhere — not «Создать аккаунт»), Pro → «Попробовать Pro» (`mailto:pro@skatelab.ru`), Coach → «Связаться с нами» (Telegram bot link `https://t.me/SkateLabBot`).

**Payment integration** (ЮKassa) is out of scope for this sprint. Pro and Coach CTAs link to contact channels until payment flow is implemented.

**GSAP:** Staggered entrance from `opacity: 0, y: 30` (not scale — scale causes subpixel text blur on 1x displays). Pro card entrance slightly delayed for emphasis.

**Annual toggle:** Optional. «Годовая подписка — скидка 20%». Show monthly price by default, toggle to annual. Not critical for MVP.

### 7. FAQ

**5-7 questions** from CustDev pain points:

1. Нужна ли специальная камера? → Нет, достаточно телефона. MP4, MOV, WebM до 500 МБ.
2. Какие элементы распознаются? → 8 элементов: тройка, вальсовый, перекидной, флип, сальхов, петля, лютц, аксель.
3. Нужен ли датчик/IMU? → Нет. Видеоанализ работает без дополнительного оборудования. IMU-датчики — опциональное улучшение точности.
4. Насколько точны метрики? → Точность высоты ЦМТ ±2 см, доворота ±5°. Основано на centre-of-mass траектории, не времени полёта.
5. Сколько стоит? → Бесплатно 3 анализа в месяц. Pro — 990 ₽/мес за безлимит. Для тренеров — от 3,500 ₽/мес.
6. Данные хранятся безопасно? → Видео хранятся в зашифрованном хранилище. Биометрические данные обрабатываются с вашего отдельного согласия.
7. Есть ли мобильное приложение? → Веб-приложение работает на любом устройстве. Мобильное приложение — в планах.

**Structure:** shadcn `Accordion`, `type="single" collapsible`. Max-width: `max-w-3xl`, centered. `id="faq" tabindex="-1"` for anchor navigation.

**SEO:** JSON-LD `FAQPage` schema injected via `<script type="application/ld+json">`. Schema content MUST be derived from the same i18n translation keys as the visible accordion to prevent content mismatches.

**FAQ Q5 reframed:** Instead of restating prices, link to pricing section: «Да, есть бесплатный тариф — 3 анализа в месяц без подписки. Для регулярных тренировок — Pro от 990 ₽/мес. См. [Тарифы](#pricing) для подробностей.»

**GSAP:** Fade-up on scroll for the section header only. Accordion is interactive, no scroll animation needed.

### 8. CTA Section

**Structure:** Full-width teal band (`sh-teal-band`). Left-aligned text.

**Copy (from CustDev taglines):**
- Eyebrow: «Начните сегодня»
- H2: «Тренируй по данным, а не на ощущениях»
- Subtitle: «Первый анализ — бесплатно. Без подписки, без обязательств.»
- CTA: «Начать бесплатно» (on-teal button, unified label), «Уже есть аккаунт?» (ghost link in `on-dark-mute` color with `underline`, not pure white — to create visual hierarchy)

**GSAP:** Fade-up entrance.

### 9. Footer

**Structure:** `<footer role="contentinfo">`, `border-t border-hairline`, white/canvas background. `max-w-5xl` container.

**Layout:** `md:grid-cols-2 lg:grid-cols-4` on desktop, 2x2 on tablet, stacked on mobile.

**Columns:**
1. **Brand:** SkateLab wordmark + tagline «Твой прыжок в цифрах» + small CTA «Начать бесплатно» text link below tagline
2. **Product:** `<nav aria-label="Продукт">` — Как это работает / Тарифы / FAQ (anchor scroll links)
3. **Legal:** `<nav aria-label="Правовая информация">` — Пользовательское соглашение / Оферта / Политика конфиденциальности / Cookie Policy. Stub pages include clear «Назад» link. External links open in new tab.
4. **Contact:** `<div aria-label="Контакты">` — Telegram / VK icons + links (`target="_blank" rel="noopener noreferrer"`)

**Bottom bar:** `border-t` separator. `© 2026 SkateLab. Все права защищены.` Footer links: `min-h-[44px]` touch targets.

### 10. Cookie Banner

**Structure:** Fixed bottom bar, `z-50`. Shown only on first visit (localStorage flag). `role="dialog" aria-modal="true" aria-labelledby="cookie-heading"`.

**Focus management:** On appear, move focus to «Принять» button. Trap Tab/Shift+Tab within banner. Escape key dismisses. Restore focus to previously active element on close.

**Visual:** Background `canvas-soft`, `border-t border-hairline`, `shadow-lg shadow-primary/5`. Button `bg-primary text-primary-foreground`. Link in `text-link` color. `max-w-5xl` internal container. Safe area: `bottom: env(safe-area-inset-bottom)` or `pb-[env(safe-area-inset-bottom)]`.

**Content:** «Мы используем cookies для работы сервиса. Продолжая, вы соглашаетесь с Cookie Policy.» + sr-only H2 heading for `aria-labelledby`.
**Action:** Button «Принять» (min-h-[44px]) → sets localStorage flag, hides banner. **Backend:** store consent in User table (`consent_accepted_at: timestamp`, `consent_categories: ["analytics"]`) at registration time (not at cookie-accept — anonymous users have no User row). localStorage is client-side display logic; DB record is 152-ФЗ audit trail.

### 11. Legal Pages

| Route | Title | Content |
|-------|-------|---------|
| `/privacy` | Политика конфиденциальности | **Real content** (template from 152-ФЗ generator). Must exist before any user registration. |
| `/terms` | Пользовательское соглашение | Stub: «Документ готовится» + link back |
| `/offer` | Оферта | Stub: «Документ готовится» + link back |
| `/cookies` | Cookie Policy | Stub: «Документ готовится» + link back |

**Privacy Policy is mandatory** before collecting any personal data (152-ФЗ). Use a template service (e.g., document.ru, iubenda) or legal counsel. Other pages can remain stubs until payment integration.

### 12. Registration Consent Checkboxes

On `/register` page, add 1 required checkbox (personal data processing only, per 152-ФЗ):

1. «Я согласен на обработку персональных данных» → links to `/privacy`

**Biometric consent deferred to first video upload** (reduces registration friction). When user first uploads a video on `/upload`, show one-time consent modal: «Я согласен на обработку анонимизированных данных (биометрия скелетона)» → links to `/privacy#anonymized`. Store consent in User table.

Implementation: native `<input type="checkbox" required>` with `<label>` wrapping the text including the link. Not a custom component. Add `aria-describedby` pointing to a description of what consent means.

## GSAP Integration

### Dependencies

```bash
bun add gsap
```

Note: `@gsap/react` removed. Use a single `useLayoutEffect` + cleanup for the entire page.

### Architecture

- All GSAP code in `'use client'` components
- Register `ScrollTrigger` inside `useLayoutEffect`, never at module scope
- Use `gsap.matchMedia()` for all responsive behavior — never `window.matchMedia` directly
- Include `prefers-reduced-motion` in all matchMedia conditions
- `anticipatePin: 1` on all pinned ScrollTriggers for smoother pin transition
- Scope all animations to `useRef` containers
- `invalidateOnRefresh: true` on all ScrollTriggers for responsive
- `scrub: 1` (number) for smooth scroll-linked animations
- `ease: 'none'` for all scrub animations; `ease: "power2.out"` for all entrance animations
- Kill all ScrollTriggers on page transition via `ScrollTrigger.killAll()`
- Add `ScrollTrigger.refresh()` on `pageshow` event for back-navigation restoration
- Tree-shake: import `gsap/ScrollTrigger` only, not full bundle

### Motion Design Tokens

All animations use a consistent timing system:

| Token | Value | Usage |
|-------|-------|-------|
| stagger | 0.12s | Gap between staggered elements |
| dur-sm | 0.3s | Micro-interactions |
| dur-md | 0.5s | Section entrances |
| dur-lg | 0.8s | Hero entrance |
| ease-out | power2.out | All entrance animations |
| ease-scrub | none | All scroll-scrub animations |

### Animation Spec

| Section | Animation | Trigger | Duration |
|---------|-----------|---------|----------|
| Header | bg opacity transition | scroll past hero | scrub |
| Hero | staggered fade-up (0.12s) | page load | 0.8s each |
| How It Works | staggered fade-up cards (0.12s) | top 80% viewport | 0.5s each |
| Demo | pinned 3-phase timeline | scroll | scrub, end +=100% |
| Trust stats | counter animation (proportional) | top 80% viewport | 0.6-1.0s |
| Pricing | staggered fade-up (0.12s) | top 85% viewport | 0.5s each |
| FAQ | header fade-up only | top 90% viewport | 0.6s |
| CTA | fade-up | top 85% viewport | 0.6s |

### Mobile Fallbacks

- Pinned demo → unpinned, 3 static phase cards (breakpoint: 1024px, not 768px)
- Parallax → disabled (respects `prefers-reduced-motion`)
- Counter animations → show final value immediately if reduced-motion
- Staggered entrances → simultaneous if reduced-motion
- Hero CSS animation classes removed — GSAP handles everything

### Reduced Motion

Global handler — applies to ALL animations:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

GSAP: set all animated elements to final state immediately. Disable all ScrollTriggers. Pinned demo → 3 static cards regardless of viewport. Header transition → instant swap. Hover effects → instant color change.

### Section Connective Tissue

Add gradient bridges between sections with sharp color contrast (hero→body: ~80-120px gradient fade from primary-deep to transparent). Use consistent `py-20 md:py-28` for content sections, `py-24 md:py-32` for hero/CTA. Add `border-t border-hairline` between all white-canvas sections for visual rhythm. Group sections by background: hero (dark), How It Works + Trust Wall (white), Demo (canvas-soft), Pricing + FAQ (white), CTA (teal).

## Typography Amendments

Changes to the `sh-*` type scale in globals.css:

1. **sh-display-xxl min raised**: `clamp(2.75rem, 7vw, 4.5rem)` — was `clamp(2.25rem, 5.5vw, 4rem)`. Ensures H1/H2 ratio ≥1.25x on mobile.
2. **Display line-height responsive**: `line-height: 1.05` at `< 768px`, `0.96` at `≥ 768px`. Prevents glyph collision on mobile wrap.
3. **Weight scale shift**: Body/secondary → 400 (Regular), Headings → 600 (SemiBold), Display accents → 700 (Bold). Current 460/540 is imperceptible hierarchy on landing pages.
4. **sh-body-strong removed**: Orphan size (1.172rem). Use `sh-body-lg` + `font-bold` utility instead.
5. **sh-price added**: `clamp(2.25rem, 4vw, 3rem), font-weight: 700, line-height: 1, letter-spacing: -0.03em`. Dedicated type for pricing numbers.
6. **sh-legal added**: `0.6875rem (11px), weight 460, line-height 1.5`. For footer copyright, legal disclaimers.
7. **Body font-variation-settings removed**: Prevents inheritance conflicts with Tailwind `font-weight` utilities. Set only on `sh-*` classes.

## Color Token Amendments

Changes to CSS variables in globals.css:

1. **on-dark-faint raised**: `oklch(0.6 0.03 280)` — was `oklch(0.42 0.03 280)`. Old value = 2.26:1 CR (FAIL). New = 4.52:1 (PASS AA on primary).
2. **sh-badge-opaque opacity**: 0.92-0.95 — was 0.85. Prevents borderline contrast on bright ice backgrounds.
3. **Dark mode on landing**: Force light theme. Add `forcedTheme="light"` to ThemeProvider or `<html class="light" suppressHydrationWarning>` on landing route.
4. **violet-soft on white**: NOT allowed as text color (1.64:1 FAIL). Use `--primary` (dark indigo) for text on white backgrounds. violet-soft only on dark backgrounds.
5. **Trust counters**: Use `text-primary` on white, not `text-surface-violet-soft`.
6. **Pro pricing highlight**: `ring-2 ring-surface-violet-soft` + shadow + «Популярный» badge. Multi-signal, not color-only.
7. **step-watermark**: Raise opacity to 0.25 with `oklch(0.7 0.006 80 / 0.25)` for visibility.

## Image Strategy

### Images (Self-hosted)

| Location | Source | Alt text | Size | Loading |
|----------|--------|----------|------|---------|
| Hero right | `/public/images/hero-skater.webp` | Figure skater performing a jump on ice | 800×1000 | `priority` (next/image) |
| Demo background | `/public/images/demo-skater.webp` | Same image, cropped for 16:9 | 1200×675 | `loading="lazy"` |

**Download stock photos from Unsplash, optimize to WebP, place in `/public/images/`.** Self-hosted images allow `next/image` with automatic optimization, `priority` for LCP, and no external domain config.

### App Screenshots (future)

Replace Unsplash photos with actual product screenshots when available. Same dimensions, same skeleton overlay approach. Product screenshots outperform stock by 2-3x on conversion.

### Implementation

- Use `next/image` with self-hosted files in `/public/images/` — no external domain config needed
- `priority` prop on hero image for LCP, `loading="lazy"` on all others
- Set explicit `width`/`height` for CLS prevention
- Add `alt` text on all images
- Download Unsplash photos manually, optimize to WebP (80% quality), commit to repo

## i18n

All new copy goes into `frontend/messages/ru.json` and `en.json` under existing `landing.*` keys. New keys needed:

- `landing.howItWorksTitle`, `landing.howItWorksHeadline`
- `landing.trust.*` (title, sessionsCount, skatersCount, clubsCount)
- `landing.pricing.*` (free/pro/coach tier names, prices, features, ctas)
- `landing.faq.*` (questions, answers)
- `landing.footer.*` (tagline, copyright, legal labels, nav labels)
- `landing.cookie.*` (text, accept button)
- `landing.consent.*` (personalData only — biometric deferred to upload)
- `landing.demo.*` (phase labels, pipeline text)
- `landing.hero.*` (secondary CTA «Смотреть демо»)

## Accessibility

- All sections use semantic HTML: `<header role="banner">`, `<nav aria-label>`, `<main id="main-content">`, `<section>`, `<footer role="contentinfo">`
- `aria-label` on all sections
- Skip-to-content link: `<a href="#main-content" class="sr-only focus:not-sr-only">Перейти к основному содержимому</a>` as first focusable element
- SkeletonPose: `role="img" aria-label="AI отслеживает 17 ключевых точек тела"` (not `aria-hidden="true"` — it conveys product meaning)
- Decorative SVGs (scroll arrow): `aria-hidden="true"`
- Focus-visible on all interactive elements
- All interactive elements: min 44x44px touch target (`min-h-[44px] min-w-[44px]`)
- Anchor targets: `id` + `tabindex="-1"` + programmatic focus after smooth scroll
- Cookie banner: `role="dialog" aria-modal="true" aria-labelledby="cookie-heading"`, focus trap, Escape dismissal, focus restoration
- FAQ: proper accordion ARIA (controls, expanded states). JSON-LD derived from same i18n keys as visible accordion.
- Pricing: `<article>` per card, `<data value="990">990 ₽</data>` for price, `<ul>/<li>` for features, «Популярный» text badge on Pro (not color-only)
- Color contrast: all text meets WCAG AA (4.5:1 for body, 3:1 for large text)
- `prefers-contrast: more`: override `--ink-faint` to `--ink-mute`, override `--on-dark-faint` to `--on-dark-mute`
- Font: preload Inter Variable. Verify `font-display: swap` in fontsource package.
- Remove `font-variation-settings: "wght" 460` from `body` rule — causes inheritance conflicts with Tailwind `font-bold`

## Performance Targets

| Metric | Target | Technique |
|--------|--------|-----------|
| LCP | < 2.5s | Preload hero image + Inter Variable font, `priority` on next/image |
| CLS | < 0.1 | Explicit width/height on all images, font-display: swap |
| INP | < 200ms | Defer GSAP init, use composited transforms only |
| JS bundle | < 150KB | Tree-shake GSAP, code-split heavy sections |

## No-JS / SSR Fallback

All animated elements must be visible without JavaScript. GSAP sets initial `opacity:0` via inline styles or classes — if JS fails, the page is blank.

**Rule:** GSAP `from()` states (initial hidden position) must be set by GSAP, not by CSS. Elements render in their final visible state by default. GSAP `from()` sets them to `opacity:0, y:30` and animates to the already-rendered final state. This way, if GSAP never runs, elements stay visible.

```js
// CORRECT: from() starts at hidden, animates to visible (already rendered)
gsap.from(element, { opacity: 0, y: 30, duration: 0.5 })

// WRONG: to() requires initial hidden state in CSS — breaks without JS
gsap.to(element, { opacity: 1, y: 0 }) // element must start at opacity:0 in CSS
```

Remove all CSS classes that set initial hidden states (`.hero-eyebrow { opacity: 0 }`, `.hero-headline { opacity: 0 }`, etc.). GSAP `from()` handles this at runtime.

**Pinned demo without JS:** Show the final phase (metrics HUD) as a static image. Use `<noscript>` to render a fallback if needed, or simply let the demo section render its final state.

## Browser Compatibility

| Feature | Support | Fallback |
|---------|---------|----------|
| `oklch()` | Safari 15.4+, Chrome 111+, Firefox 113+ | Add `@supports (color: oklch(0 0 0))` guard. For unsupported browsers, provide sRGB fallback via `@supports not` block using hex values. |
| `dvh` | Safari 15.4+, Chrome 108+ | `height: 100vh` fallback before `height: 100dvh` |
| `font-variation-settings` | All modern | No fallback needed — Inter Variable falls back to weight axis |
| GSAP ScrollTrigger | All modern | No-JS fallback above |

**oklch strategy:** The existing CSS uses oklch for all tokens. If the target audience includes older Safari (< 15.4), add an `@supports not (color: oklch(0 0 0))` block at the end of globals.css mapping all tokens to hex equivalents. If targeting only modern browsers (Chrome 111+, Safari 15.4+), no fallback needed.

## Out of Scope

- Legal document texts for Terms, Offer, Cookies (stubs only — Privacy Policy must be real)
- Real testimonial quotes (removed entirely until post-pilot)
- Real partner logos (use animated counters instead)
- Annual pricing toggle
- Mobile app download links
- A/B testing infrastructure
- Unicorn Studio / WebGL shader backgrounds
- Payment integration (ЮKassa) — Pro/Coach CTAs link to contact channels
- SkeletonPose CSS-only animation (current setInterval approach works; CSS rewrite is low priority)
- Annual pricing toggle
- Mobile app download links
