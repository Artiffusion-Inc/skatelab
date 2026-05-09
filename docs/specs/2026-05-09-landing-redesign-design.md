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

**Mobile:** Hamburger menu with full specification:
- Hamburger icon button (Lucide `Menu`), 44×44px touch target, `aria-label="Открыть меню"`, `aria-expanded` toggled on open/close
- Slide-in panel from right: `transform translateX(100%) → translateX(0)`, `0.3s ease-out` (matches `dur-sm` motion token)
- Backdrop: `fixed inset-0`, `bg-black/50`, opacity `0 → 1` over `0.2s ease-out`
- Z-index hierarchy: mobile CTA bar `z-40`, sticky header `z-50`, panel backdrop `z-[55]`, panel `z-[60]`, cookie banner `z-[70]`
- Panel width: `min(80vw, 280px)`, full height, `bg-background`
- Body scroll lock when panel open (`overflow: hidden` on `<body>`)
- Focus trap: `react-focus-lock` with `returnFocus`. Focus moves to panel on open, returns to hamburger button on close
- `prefers-reduced-motion`: instant show/hide, no transitions
- Panel dismiss: close button (X icon, top-right, 44×44px, `aria-label="Закрыть меню"`) + backdrop click + Escape key. NO swipe-to-dismiss
- Panel content: exactly 3 nav links matching desktop (Как это работает, Тарифы, FAQ) as full-width tap targets (`py-4`, `text-lg`, `border-b border-hairline`). CTA stays outside panel in sticky header. No footer links or social links in panel
- Link behavior: tap closes panel first, then smooth-scrolls to anchor target
- Sticky header on mobile: logo (left) + hamburger icon (right). CTA button visible in header when space allows, otherwise hidden behind hamburger
- Cookie banner conflict: hide mobile CTA bar while cookie banner visible

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

**Mobile CTA visibility:** Reduce hero padding on mobile (`py-8 sm:py-16 lg:py-0`). Ensure CTA buttons visible above fold on 375x667 iPhone SE. Consider sticky mobile CTA bar (fixed bottom, `z-40`, `md:hidden`) with single «Начать бесплатно» button. **Important:** Hide the mobile CTA bar while the cookie banner is visible (use `className={showCookieBanner ? 'hidden md:flex' : 'flex'}`) to avoid overlapping interactive elements. After cookie acceptance, the CTA bar appears.

**Hero-to-body transition:** Add gradient fade zone (~80-120px) at hero bottom: `bg-gradient-to-b from-primary-deep via-primary-deep/50 to-transparent`. Prevents hard edge where dark hero meets white body.

**GSAP:** Staggered fade-up entrance with consistent 0.12s stagger (not irregular 0.2/0.3s gaps). Remove CSS hero animation classes — use GSAP for all motion. **Flash prevention:** In `useLayoutEffect`, call `gsap.set()` on all animated elements before starting timelines. This hides elements synchronously before paint, preventing the flash-of-content that would occur if elements render visible during hydration then get hidden by `gsap.from()`. Pattern: `gsap.set('.hero-eyebrow, .hero-headline, .hero-subtitle, .hero-cta', { opacity: 0, y: 30 })` then `gsap.from()` with same values animates them in.

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

### 4. Trust Wall (Animated Counters)

**KILLER FEATURE.** This is the product demo shown through scroll.

**Structure:**
- Container: `max-w-5xl`, `aspect-video`, centered. `id="demo" tabindex="-1"` for anchor navigation.
- Pin: `scrollTrigger: { pin: true, scrub: 1, end: '+=150%', anticipatePin: 0.1 }` (+=150% gives ~400px per phase on desktop — enough for smooth transitions without 3-viewport fatigue).
- 3 phases scrubbed by scroll position (0-33%, 33-66%, 66-100%) — evenly distributed:
  1. **Raw video** — stock skating image, no overlay
  2. **Skeleton overlay** — same image + SkeletonPose + dark overlay
  3. **Metrics HUD** — skeleton + 3 opaque metric badges (Высота ЦМТ, Доворот, Время полёта) + tech spec strip

**Below pinned area:** Text «Видео → Скелетон → Метрики за 12 секунд» as a pipeline explanation.

**Keyboard accessibility:** Add phase navigation controls using the WAI-ARIA Radio Group Pattern: `role="radiogroup" aria-label="Фазы демо"` containing 3 `role="radio"` elements with `aria-checked`, `tabindex="0"` on active radio and `tabindex="-1"` on inactive radios (roving tabindex). ArrowRight/ArrowLeft moves between radios and updates the demo phase. Each radio also has a visible text label (not just a colored dot): «1. Исходное видео», «2. Скелетон тела», «3. Биомеханические метрики».

**Mobile/tablet (< 1024px):** No pin. Simple `whileInView` entrance animation via `gsap.matchMedia()`. 3 static phase cards stacked vertically (before/after style), each with the image at that phase. Pin breakpoint changed from 768px to 1024px — tablets should not get pinned scroll (poor UX with touch).

**Reduced-motion:** Under `prefers-reduced-motion: reduce`, show 3 static phase cards regardless of viewport width. Disable pin entirely. Add to GSAP matchMedia: `(min-width: 1024px) and (prefers-reduced-motion: no-preference)`.

**GSAP timeline:**
```
const mm = gsap.matchMedia()

mm.add("(min-width: 1024px) and (prefers-reduced-motion: no-preference)", () => {
  // Desktop: pinned 3-phase scroll, evenly distributed
  gsap.timeline({
    scrollTrigger: { trigger, pin: true, scrub: 1, end: '+=150%', anticipatePin: 0.1 }
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

**Back-navigation:** Add `ScrollTrigger.refresh()` on `pageshow` event (with `event.persisted` check) to fix scroll restoration after bfcache navigation. Clean up the listener on unmount:
```js
useEffect(() => {
  const onPageShow = (e) => { if (e.persisted) ScrollTrigger.refresh() }
  window.addEventListener('pageshow', onPageShow)
  return () => window.removeEventListener('pageshow', onPageShow)
}, [])
```

**Badge contrast:** Raise `sh-badge-opaque` opacity from 0.85 to 0.92-0.95 to guarantee text readability on bright ice backgrounds.

### 5. Demo Section (GSAP pinned scroll)

**No placeholder testimonials.** Fake quotes damage credibility. Trust wall uses only animated counters until real testimonials available post-pilot.

**Animated counters:**
- «1,200+ сессий проанализировано»
- «340+ фигуристов»
- «15+ клубов»

**Section heading:** H2 `sh-display-xl text-ink` — «Нам доверяют» or sr-only heading if visually minimal design preferred.

**Layout:** `lg:grid-cols-3`, centered (changed from md: — 3 columns too tight on tablet). White canvas background (`bg-background`). Each counter: large number (`sh-display-lg font-bold text-primary` — NOT violet-soft which fails WCAG on white at 1.64:1) + label (`sh-caption text-ink-mute`).

**GSAP:** Counter animation with proportional durations (minimum 0.8s for perceptibility): 1200 → 1.0s, 340 → 0.9s, 15 → 0.8s. All use `ease: "power2.out"`.

**Data source:** Counter values are i18n strings in `messages/ru.json` under keys `landing.trustSessionsValue`, `landing.trustSkatersValue`, `landing.trustClubsValue`. Values must reflect verified real data (152-ФЗ compliance). Update via PR with a comment noting the data source and date (e.g., `// As of 2026-05-09: 1,247 sessions from production DB`). No API endpoint needed — these numbers change at most weekly. Format: `1,200+` with `+` suffix for rounded values, exact number only when current to the day. Displaying inflated numbers violates ФЗ «О рекламе» — values must reflect real data at launch.

**Reduced motion:** Show final value immediately, no counting animation.

### 6. Pricing

**3 tiers** from unit-economics.md:

| Tier | Price | Segment | Included |
|------|-------|---------|----------|
| **Free** | 0 ₽/мес | Начинающие | 3 анализа/мес, базовый скелетон |
| **Pro** | 990 ₽/мес | Фигуристы | Безлимит анализов, рекомендации, прогресс, сравнение с эталоном |
| **Coach** | 3,500 ₽/мес | Тренеры | Dashboard учеников, диагностика, отчёты, до 20 учеников |

**Layout:** `lg:grid-cols-3`, centered (changed from md: — 3 columns too tight on tablet for Russian text). Pro card multi-signal highlight: `ring-2 ring-surface-violet-soft` + `shadow-sm shadow-surface-violet-soft/20` + «Популярный» text badge at top. Not just ring-2 ring-primary (too thin, indistinguishable). Each card: tier name, price, description, feature list (✓ check icons in `<ul>/<li>`), CTA button. Price uses `sh-price` class (`clamp(2.25rem, 4vw, 3rem), font-weight: 700, line-height: 1, letter-spacing: -0.03em`).

**CTA copy (unified):** Free → «Начать бесплатно» (same label everywhere — not «Создать аккаунт»), Pro → «Попробовать Pro» (Telegram `https://t.me/SkateLabPro`), Coach → «Связаться с нами» (Telegram `https://t.me/SkateLabBot`). Both Pro and Coach use Telegram for consistency — Russian users are Telegram-native. Note: `mailto:` avoided because it forces users out of the browser into an email app they may not have configured.

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

**SEO:** JSON-LD `FAQPage` schema injected via `<script type="application/ld+json">`. Schema content MUST be derived from the same i18n translation keys as the visible accordion to prevent content mismatches. **The JSON-LD must be rendered in a server component** (not inside `LandingClient.tsx`) so Googlebot can parse it. Use `getTranslations` from `next-intl/server` to read FAQ content server-side.

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

**Structure:** Fixed bottom bar, `z-[70]` (above hamburger panel at z-[60] and header at z-50). Shown only on first visit (localStorage flag). `role="dialog" aria-modal="true" aria-labelledby="cookie-heading"`.

**Focus management:** On appear, move focus to «Принять» button. Trap Tab/Shift+Tab within banner. Escape key dismisses. Restore focus to previously active element on close.

**Visual:** Background `canvas-soft`, `border-t border-hairline`, `shadow-lg shadow-primary/5`. Button `bg-primary text-primary-foreground`. Link in `text-link` color. `max-w-5xl` internal container. Safe area: `bottom: env(safe-area-inset-bottom)` or `pb-[env(safe-area-inset-bottom)]`.

**Content:** «Мы используем cookies для работы сервиса. Продолжая, вы соглашаетесь с Cookie Policy.» + sr-only H2 heading for `aria-labelledby`.
**Action:** Button «Принять» (min-h-[44px]) → sets localStorage flag, hides banner. **Backend:** store consent in User table (`consent_accepted_at: timestamp`, `consent_categories: ["analytics"]`) at registration time (not at cookie-accept — anonymous users have no User row). localStorage is client-side display logic; DB record is 152-ФЗ audit trail. For anonymous visitors, cookie consent via localStorage is accepted market practice. Analytics cookies must use anonymized identifiers. If analytics providers require verifiable consent records, implement a server-side endpoint (`POST /api/cookie-consent` with anonymous session ID).

### 11. Legal Pages

| Route | Title | Content |
|-------|-------|---------|
| `/privacy` | Политика конфиденциальности | **Real content** (template from 152-ФЗ generator). Must exist before any user registration. |
| `/terms` | Пользовательское соглашение | Stub: «Документ готовится» + link to homepage |
| `/offer` | Оферта | Stub: «Документ готовится» + link to homepage |
| `/cookies` | Cookie Policy | Stub: «Документ готовится» + link to homepage |

All legal pages share a minimal layout with SkateLab wordmark + «На главную» link in the header. Include breadcrumbs (`Главная > Правовая информация > Политика конфиденциальности`). Each page has a proper `<h1>` matching the title. Do NOT use `history.back()` — it can take users off-site. The `/cookies` page must list all cookies set, their purposes, and retention periods (152-ФЗ requirement).

**Privacy Policy is mandatory** before collecting any personal data (152-ФЗ). Use a template service (e.g., document.ru, iubenda) or legal counsel. Other pages can remain stubs until payment integration.

### 12. Registration Consent Checkboxes

On `/register` page, add 1 required checkbox (personal data processing only, per 152-ФЗ):

1. «Я согласен на обработку персональных данных» → links to `/privacy`

**Biometric consent deferred to first video upload** (reduces registration friction). When user first uploads a video on `/upload`, show one-time consent modal: «Я согласен на обработку анонимизированных данных (биометрия скелетона)» → links to `/privacy#anonymized`. Store consent in User table.

Implementation: native `<input type="checkbox" required>` with `<label>` wrapping the text including the link. Not a custom component. Add `aria-describedby` pointing to a description of what consent means.

**Biometric consent modal accessibility:**
- `role="dialog" aria-modal="true" aria-labelledby="biometric-consent-title"` on the overlay container
- Focus trap using `react-focus-lock` (same as cookie banner) with `returnFocus`
- On open, move focus to the modal container or the checkbox
- Escape key closes the modal and restores focus to the triggering element
- Prevent background page scroll while modal is open (`overflow: hidden` on `<body>`)
- The «Подтвердить и продолжить» button uses native `disabled` attribute — screen readers announce it as "unavailable" until the checkbox is checked

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
- `anticipatePin: 0.1` on pinned ScrollTriggers (0.1s anticipation, not 1s which is too aggressive)
- Scope all animations to `useRef` containers
- `invalidateOnRefresh: true` on all ScrollTriggers for responsive
- `scrub: 1` (number) for smooth scroll-linked animations
- `ease: 'none'` for all scrub animations; `ease: "power2.out"` for all entrance animations
- Never use `ScrollTrigger.killAll()` — it is global and kills ScrollTriggers from other pages/components. Use only `ctx.revert()` which is scoped to the GSAP context.
- Add `ScrollTrigger.refresh()` on `pageshow` event (with `event.persisted` check) for bfcache restoration. Clean up the listener on unmount.
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
| Demo | pinned 3-phase timeline | scroll | scrub, end +=150% |
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

Add gradient bridges between sections with sharp color contrast (hero→body: ~80-120px gradient fade from primary-deep to transparent). Use consistent `py-20 md:py-28` for content sections, `py-24 md:py-32` for hero/CTA. Add `border-t border-hairline` between all white-canvas sections for visual rhythm. Group sections by background: hero (dark) → How It Works (white) → Trust Wall (white) → Demo (canvas-soft) → Pricing (white) → FAQ (white) → CTA (teal).

## Typography Amendments

Changes to the `sh-*` type scale in globals.css:

1. **sh-display-xxl**: `clamp(2.75rem, 7vw, 4.5rem)`, `font-variation-settings: "wght" 540`, `font-weight: 540`. `line-height: 1.05` default, `0.96` at `≥ 768px` (via media query). Ensures H1/H2 ratio ≥1.57x on mobile.
2. **sh-display-xl**: Keep `clamp(2rem, 4vw, 3rem)`. `line-height: 1.05` default, `0.96` at `≥ 768px`.
3. **Weight scale shift (landing-page scoped only)**: Add `.landing-page` wrapper class. Within it, override: body → 400, headings → 600, display accents → 700. Do NOT change global weight scale (would affect existing app components). Note: `.landing-page body` selector won't work if `.landing-page` is on a `<div>` (body is an ancestor, not descendant). Use `body:has(.landing-page)` or put the class directly on `<body>`. Implementation:
   ```css
   body:has(.landing-page) { font-variation-settings: "wght" 400; font-weight: 400; }
   .landing-page .sh-display-xxl { font-variation-settings: "wght" 700; font-weight: 700; }
   .landing-page .sh-display-xl { font-variation-settings: "wght" 600; font-weight: 600; }
   .landing-page .sh-heading-lg { font-variation-settings: "wght" 600; font-weight: 600; }
   ```
   **shadcn components** retain their own font-weight via Tailwind utilities (e.g., `font-medium` = 500). The `.landing-page` overrides only affect elements using `sh-*` type classes. FAQ Accordion triggers explicitly set `font-semibold` to avoid inheritance.
4. **sh-body-strong removed**: Orphan size (1.172rem). Use `sh-body-lg` + `font-bold` utility instead. Search codebase for usages first.
5. **sh-price added**: `font-size: clamp(2.25rem, 4vw, 3rem); font-weight: 700; font-variation-settings: "wght" 700; line-height: 1; letter-spacing: -0.03em;`
6. **sh-legal added**: `font-size: 0.6875rem; font-weight: 460; font-variation-settings: "wght" 460; line-height: 1.5;`
7. **Body font-variation-settings**: Remove `font-variation-settings: "wght" 460` from `body` rule in globals.css. Audit all components that depend on inherited `font-variation-settings` — search for `font-weight` usage without corresponding `font-variation-settings`. Add `font-variation-settings` overrides where needed.

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

All new copy goes into `frontend/messages/ru.json` and `en.json` under existing `landing.*` keys. **Use flat keys consistent with existing pattern** — no nested objects. Existing keys like `landing.featuresTitle`, `landing.featuresHeadline` use flat keys, not nested namespaces.

**Key renames (existing → new):**
- `landing.featuresTitle` → `landing.howItWorksTitle`
- `landing.featuresHeadline` → `landing.howItWorksHeadline`
- `landing.ctaSecondary` value changes from «Как это работает» → «Смотреть демо»
- `landing.ctaAction` is deprecated — use `landing.ctaPrimary` («Начать бесплатно») everywhere

**New flat keys:**
- `landing.howItWorksTitle`, `landing.howItWorksHeadline`, `landing.howItWorksStep1Title`, `landing.howItWorksStep1Accent`, etc.
- `landing.trustTitle`, `landing.trustSessionsLabel`, `landing.trustSkatersLabel`, `landing.trustClubsLabel`
- `landing.pricingFreeName`, `landing.pricingFreePrice`, `landing.pricingFreeFeatures`, etc.
- `landing.faqQ1`, `landing.faqA1`, etc.
- `landing.footerTagline`, `landing.footerCopyright`, etc.
- `landing.cookieText`, `landing.cookieAccept`
- `landing.consentPersonalDataLabel`, `landing.consentBiometricLabel`
- `landing.demoPhase1Label`, `landing.demoPhase2Label`, `landing.demoPhase3Label`, `landing.demoPipelineText`

## Accessibility

- All sections use semantic HTML: `<header role="banner">`, `<nav aria-label>`, `<main id="main-content">`, `<section>`, `<footer role="contentinfo">`
- `aria-label` on all sections
- Skip-to-content link: `<a href="#main-content" class="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-4 focus-visible:left-4 focus-visible:z-[100] focus-visible:bg-primary focus-visible:text-primary-foreground focus-visible:px-4 focus-visible:py-2 focus-visible:rounded">Перейти к основному содержимому</a>` as first focusable element. Target `<main id="main-content" tabindex="-1">` must exist — `tabindex="-1"` is required for Safari focus movement.
- SkeletonPose: `role="img" aria-label="AI отслеживает 17 ключевых точек тела"` in the hero (always visible). In the demo section, SkeletonPose must be **conditionally rendered** — not rendered at all in phase 1 (raw video), rendered with `aria-label` in phases 2-3. Do NOT render SkeletonPose with `opacity: 0` in phase 1; invisible but accessible content contradicts what the user sees.
- Decorative SVGs (scroll arrow): `aria-hidden="true"`
- Focus-visible on all interactive elements
- All interactive elements: min 44x44px touch target (`min-h-[44px] min-w-[44px]`)
- Anchor targets: `id` + `tabindex="-1"` + programmatic focus after smooth scroll
- Cookie banner: `role="dialog" aria-modal="true" aria-labelledby="cookie-heading"`, focus trap (react-focus-lock with `returnFocus`), Escape dismissal, focus restoration. Add `aria-live="polite"` wrapper for screen reader announcement on appear. Auto-focus the «Принять» button within the FocusLock.
- FAQ: proper accordion ARIA (controls, expanded states). JSON-LD derived from same i18n keys as visible accordion.
- Pricing: `<section aria-labelledby="pricing-heading">` wrapper. Each card as `<li>` inside `<ul>` (list of pricing options, not `<article>` — pricing cards are not independently distributable content). `<data value="990">990 ₽</data>` for price, `<ul>/<li>` for features, «Популярный» text badge on Pro (not color-only).
- Color contrast: all text meets WCAG AA (4.5:1 for body, 3:1 for large text)
- `prefers-contrast: more`: override `--ink-faint` to `--ink-mute`, override `--on-dark-faint` to `--on-dark-mute`
- Font: preload Inter Variable. Verify `font-display: swap` in fontsource package.
- Remove `font-variation-settings: "wght" 460` from `body` rule — causes inheritance conflicts with Tailwind `font-bold`

## SEO & Meta Tags

The landing page requires its own `generateMetadata()` export (not inherited from root layout):

```tsx
export async function generateMetadata(): Promise<Metadata> {
  return {
    title: "SkateLab — AI Тренер по фигурному катанию",
    description: "Запишите прыжок — увидьте миллиметры. AI-анализ техники: высота ЦМТ, доворот, время полёта. < 15 с на полный разбор видео.",
    alternates: { canonical: "https://skatelab.ru" },
    openGraph: {
      title: "SkateLab — AI Тренер по фигурному катанию",
      description: "Запишите прыжок — увидьте миллиметры. AI-анализ техники за < 15 секунд.",
      url: "https://skatelab.ru",
      siteName: "SkateLab",
      locale: "ru_RU",
      type: "website",
      images: [{ url: "/images/og-image.png", width: 1200, height: 630, alt: "SkateLab — AI анализ фигурного катания" }],
    },
  }
}
```

Create an OG image (1200×630px) at `/public/images/og-image.png` with the SkateLab wordmark, tagline, and visual proof (skeleton overlay). The JSON-LD FAQ schema must be rendered in a **server component** (not inside `LandingClient.tsx`) so Googlebot can parse it. Use `getTranslations` from `next-intl/server` to read FAQ content server-side.

## Font Strategy

The current `@import "@fontsource-variable/inter"` in globals.css creates a CSS waterfall that delays font discovery. For the landing page (LCP-critical), migrate to `next/font/local`:

1. Copy `inter-latin-wght-normal.woff2` and `inter-cyrillic-wght-normal.woff2` from the fontsource package to `/public/fonts/`
2. In the landing page server component, use `next/font/local`:
   ```tsx
   import localFont from 'next/font/local'
   const inter = localFont({
     src: [
       { path: '../../public/fonts/inter-latin-wght-normal.woff2', style: 'normal' },
       { path: '../../public/fonts/inter-cyrillic-wght-normal.woff2', style: 'normal' },
     ],
     variable: '--font-inter',
     display: 'swap',
   })
   ```
3. This gives automatic font preloading, `font-display: swap`, and eliminates the CSS import waterfall.

The root layout can continue using `@fontsource-variable/inter` for app pages. Only the landing page needs the optimized font loading.

## Analytics Events (PostHog Self-Hosted — Future)

Analytics are **out of scope for MVP landing page**. The implementation will use **PostHog self-hosted** when deployed, not Yandex.Metrika or any third-party SaaS analytics.

**When analytics is added (post-MVP):**
- PostHog self-hosted instance, initialized after cookie consent
- Event taxonomy for the landing page:

| Event Name | Trigger | Purpose |
|------------|---------|---------|
| `landing_cta_primary` | Click "Начать бесплатно" (any instance) | Primary conversion |
| `landing_cta_demo` | Click "Смотреть демо" | Engagement |
| `landing_pricing_pro` | Click "Попробовать Pro" | Monetization intent |
| `landing_pricing_coach` | Click "Связаться с нами" (Coach) | B2B intent |
| `landing_scroll_demo` | Demo section enters viewport | Engagement depth |
| `landing_faq_expand` | Open FAQ accordion item | Content interest |

- Cookie consent gates all analytics initialization (152-ФЗ compliance)
- No analytics scripts loaded before consent banner acceptance

## Performance Targets

| Metric | Target | Technique |
|--------|--------|-----------|
| LCP | < 2.5s | Preload hero image + Inter Variable font, `priority` on next/image |
| CLS | < 0.1 | Explicit width/height on all images, font-display: swap |
| INP | < 200ms | Defer GSAP init, use composited transforms only |
| JS bundle (page-specific) | < 100KB gzip | GSAP core + ScrollTrigger ≈ 46KB gzip, remaining budget for components |
| Total page JS | ~220KB gzip | Includes Next.js framework (~130KB) — not controllable |

## Favicon & OG Image

- **Favicon:** Use existing `/public/favicon.svg` (48×46 violet figure skate icon). Next.js 16 serves it automatically. No `.ico` or multi-size PNG needed for MVP.
- **OG image:** Static `/public/images/og-image.png` (1200×630px) with SkateLab wordmark, tagline, and skeleton overlay visual. Created as a design asset, not auto-generated. PostHog or `@vercel/og` for dynamic OG can be added post-MVP if needed.
- **robots.txt:** Not a launch blocker. Add post-MVP: allow `/` and `/register`, disallow authenticated routes (`/feed`, `/upload`, `/profile`, `/settings`). Sitemap unnecessary for single-page landing.

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

**oklch strategy:** Target modern browsers only (Chrome 111+, Safari 15.4+, Firefox 113+). All target devices support oklch. No `@supports not` fallback block needed. If a legacy browser is later required, add hex equivalents at that time.

## GSAP Architecture Detail

### Client Boundary

Landing page uses Next.js App Router. `LandingPage` is a server component (`page.tsx`). GSAP requires `'use client'`.

**Pattern:** Create `LandingClient.tsx` as the single client boundary. It imports GSAP, registers ScrollTrigger, and orchestrates all animations via one `useLayoutEffect`. Server component (`page.tsx`) renders `<LandingClient />` and passes i18n strings as props.

```
app/page.tsx (server) → LandingClient.tsx ('use client') → all sections as children
```

`LandingClient.tsx` holds:
- `gsap.registerPlugin(ScrollTrigger)` (called once)
- Single `useLayoutEffect` that creates a GSAP context, runs `gsap.matchMedia()`, and returns cleanup
- `ScrollTrigger.killAll()` in cleanup on unmount

Individual section components (`HeroSection`, `DemoSection`, etc.) remain `'use client'` but do NOT register their own ScrollTriggers. They expose `useRef` containers that `LandingClient` queries for animation targets.

### No-JS Implementation Pattern

All section components render in their **final visible state** by default. No CSS classes that set `opacity: 0` or `transform: translateY(20px)`. GSAP `from()` creates the hidden initial state at runtime:

```tsx
// In LandingClient useLayoutEffect
const ctx = gsap.context(() => {
  // Set initial hidden state synchronously before paint (prevents flash of visible content during hydration)
  gsap.set('.hero-eyebrow, .hero-headline, .hero-subtitle, .hero-cta, .hero-scroll', { opacity: 0, y: 20 })
  // Then animate from hidden to visible (elements start at hidden, animate to their rendered visible state)
  gsap.from('.hero-eyebrow', { opacity: 0, y: 20, duration: 0.8, stagger: 0.12 })
  gsap.from('.hero-headline', { opacity: 0, y: 30, duration: 0.8 }, 0.12)
  // ...
})
return () => ctx.revert() // restores elements to their original (visible) state
```

**Flash prevention:** `gsap.set()` runs synchronously in `useLayoutEffect` before the browser paints. This prevents the 1-frame flash where elements are visible during hydration, then hidden by `gsap.from()`. Without `gsap.set()`, there would be a visible flash (FOC). If JS fails entirely, neither `gsap.set()` nor `gsap.from()` runs, elements stay visible.

### Route and Layout

Landing page lives at `/` (root). Current `app/page.tsx` does cookie-based redirect. New structure:

```
app/
├── page.tsx              # Server component, checks sb_auth cookie
│                         # Authenticated → redirect('/feed')
│                         # Not authenticated → <LandingClient />
├── layout.tsx            # Root layout (existing, with ThemeProvider)
├── (auth)/               # Auth pages (existing)
└── (app)/                # App pages (existing)
```

Force light theme on landing: Set `<html class="light" suppressHydrationWarning>` in the server-rendered output for the landing route. This guarantees no dark-mode flash — the class is set in the initial HTML before paint. `suppressHydrationWarning` is needed because next-themes may try to set a different class during hydration. Using `forcedTheme="light"` on ThemeProvider is a fallback but may cause a 1-frame flash since it runs client-side.

Add `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">` to the landing page head (required for `env(safe-area-inset-*)` to work on iOS). In Next.js, use the `viewport` export:
```tsx
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}
```
This goes in `app/layout.tsx` (applies globally, safe for all pages).

## Detailed Component Specs

### Hero Mobile Image

On mobile/tablet (`< lg`), the right column image is not hidden. Instead:

- Show the same `hero-skater.webp` with `aspect-[16/9]` (shorter crop, more horizontal)
- SkeletonPose overlay and metric badge scale down: badge uses `sh-caption` instead of `sh-heading-lg`
- Image uses `loading="lazy"` on mobile (not `priority` — hero text is the LCP element on mobile, not the image)
- Order: text column first, image second (`order-1` / `order-2`)

### Demo 3 Static Mobile Cards

On `< 1024px`, the pinned demo is replaced by 3 stacked cards:

```
Card 1: <Image src={heroSkater} />  — "Исходное видео"
Card 2: <Image src={heroSkater} /> + <SkeletonPose /> + dark overlay  — "Скелетон тела"
Card 3: <Image src={heroSkater} /> + <SkeletonPose /> + dark overlay + 3 metric badges  — "Биомеханические метрики"
```

Each card: `rounded-lg border border-hairline overflow-hidden`, with a label below the image. All 3 use the **same** source image (`demo-skater.webp`). The skeleton overlay is achieved by rendering the `SkeletonPose` SVG absolutely positioned over the image (existing component). Phase 3 adds the metric badges absolutely positioned on top.

### Scroll Offset for Sticky Header

All anchor targets (`#how-it-works`, `#demo`, `#pricing`, `#faq`, `#cta`) need `scroll-margin-top: 80px` (or `scroll-mt-20` in Tailwind) to account for the 64px sticky header + 16px breathing room.

```css
section[id] {
  scroll-margin-top: 5rem; /* 80px = 64px header + 16px gap */
}
```

### Upload Consent Modal

When user first uploads a video on `/upload`:

- **Trigger:** User clicks "Upload" or drops a file, before the upload request is sent
- **Modal:** Full-screen overlay (`fixed inset-0 z-50 bg-black/50`), centered card (`max-w-md`)
- **Content:** Title «Согласие на обработку данных» + explanation text + single checkbox «Я согласен на обработку анонимизированных данных (биометрия скелетона)» + link to `/privacy#anonymized`
- **Actions:** «Подтвердить и продолжить» (primary, disabled until checked) + «Отмена» (ghost)
- **Storage:** On confirm, PATCH `/api/users/me` with `{ biometric_consent: true, biometric_consent_at: ISO8601 }`. Store consent in User table columns `biometric_consent` (boolean) and `biometric_consent_at` (timestamp).
- **One-time:** After first consent, check `user.biometric_consent` before showing. If already true, skip modal entirely.

### Cookie Banner Focus Trap

Use `react-focus-lock` (add to dependencies: `bun add react-focus-lock`). Dynamically import the cookie banner component with `next/dynamic` (`ssr: false`) so `react-focus-lock` (~7KB gzip) is only loaded when the banner is visible, not on every page load. Pattern:

```tsx
import FocusLock from 'react-focus-lock'

{showBanner && (
  <FocusLock returnFocus>
    <div role="dialog" aria-modal="true" aria-labelledby="cookie-heading">
      <h2 id="cookie-heading" className="sr-only">Cookie consent</h2>
      <p>Мы используем cookies для работы сервиса...</p>
      <button onClick={acceptCookies} autoFocus>Принять</button>
    </div>
  </FocusLock>
)}
```

### Pro Card «Популярный» Badge

Positioned at top center of the pricing card, above the tier name:

```tsx
<div className="relative">
  <span className="absolute -top-3 left-1/2 -translate-x-1/2 sh-badge-opaque px-3 py-1 rounded-full text-xs text-primary-foreground">
    Популярный
  </span>
  {/* tier name, price, features... */}
</div>
```

Uses `sh-badge-opaque` style (dark navy background, violet-soft border) — consistent with demo metric badges.

### Footer CTA

Small text link in the brand column, below the tagline:

```tsx
<div> {/* Brand column */}
  <p className="sh-display-md text-ink">SkateLab</p>
  <p className="sh-caption text-ink-mute">Твой прыжок в цифрах</p>
  <a href="/register" className="sh-button-cap text-link hover:underline mt-2 inline-block">
    Начать бесплатно →
  </a>
</div>
```

Size: `sh-button-cap` (0.875rem, weight 600). Color: `text-link` (oklch blue). Underline on hover. No button styling — text link only, minimal visual weight.

### Gradient Bridge (Hero → Body)

Applied as a `<div>` at the bottom of the hero section, after the grid content:

```tsx
<div className="h-20 md:h-28 bg-gradient-to-b from-primary-deep via-primary-deep/50 to-transparent" aria-hidden="true" />
```

Height: `h-20` (80px) on mobile, `md:h-28` (112px) on desktop. Creates a smooth fade from the dark navy hero to the white canvas body section below.

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
