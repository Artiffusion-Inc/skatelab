# Landing Page Redesign — Design Spec

> Date: 2026-05-09
> Status: Approved
> Scope: Full landing page redesign with GSAP scroll animations, new sections, legal stubs

## Context

Current landing has 4 sections (Hero, Features, Demo, CTA). Missing: footer, navigation, testimonials, pricing, FAQ, trust indicators, legal compliance. Animations are CSS-only (fade-up, pulse). Images are Unsplash placeholders without next/image. No scroll-triggered motion.

Product positioning (from CustDev): coaches buy time savings + fewer disputes. Skaters buy faster progress. Key insight: "Измеряй технику, а не угадывай."

## Design Principles

- **Register:** Product (design serves the product, not IS the product)
- **3-canvas system:** indigo navy hero → white canvas body → deep teal closing CTA
- **Brand voice:** точный, спортивный, уверенный. Direct, no fluff. Russian-first.
- **Anti-references:** generic SaaS cream, crypto neon, health-tech softness, winter clichés
- **Color strategy:** Restrained with one accent (surface-violet-soft ≤10% on hero, surface-teal-deep on CTA)
- **Motion strategy:** Superhuman-level — GSAP ScrollTrigger for entrances, parallax, pinned demo. No WebGL shaders.

## Section Architecture (top → bottom)

### 1. Sticky Header

**Structure:** Fixed top bar. Transparent on hero → white with backdrop-blur on scroll.

**Elements:**
- Left: SkateLab wordmark (text, not logo image)
- Center: Nav links — Как это работает / Тарифы / FAQ (smooth-scroll to anchors)
- Right: CTA button «Начать бесплатно» (links to /register), or avatar+name if authenticated

**GSAP:** `onScroll` trigger at hero bottom → transition from transparent to white. Animate `background-color`, `backdrop-filter`, `border-bottom` opacity.

**Mobile:** Hamburger menu. Slide-in panel from right. CTA stays visible.

### 2. Hero Section

**Layout:** Full-viewport (min-h-[100dvh]). Grid: `lg:grid-cols-[1fr_1.1fr]` asymmetric split.

**Left column:**
- Eyebrow: `sh-micro uppercase tracking-[0.3em] text-on-dark-mute` — «AI Тренер по фигурному катанию»
- H1: `sh-display-xxl text-primary-foreground` — «Запишите прыжок.» / «Увидьте миллиметры.» (violet soft)
- Subtitle: `sh-body-lg text-on-dark-mute max-w-lg` — CustDev-validated: «Объективный биомеханический разбор: высота, доворот, стабильность приземления. Данные, которые разрешат спор тренера и ученика.»
- Stat: inline `sh-display-lg font-bold text-surface-violet-soft` — «< 15 с» + label «на полный разбор видео»
- Dual CTA: Primary «Начать бесплатно» (on-dark-pill), Secondary «Как это работает» (ghost, smooth-scroll to #how-it-works)

**Right column:**
- Stock photo of figure skater in jump (Unsplash: `photo-1590490360182-c33d57733427`) with dark overlay + SVG skeleton overlay (existing `SkeletonPose` component) + opaque metric badge (Высота ЦМТ: 1.24 м)
- Aspect ratio: `aspect-[4/5]`, `rounded-lg`, `overflow-hidden`
- `fetchPriority="high"`, explicit `width`/`height` for CLS

**GSAP:** Staggered fade-up entrance (eyebrow 0.2s → h1 0.4s → subtitle 0.7s → CTA 1s). Right column: fade-in at 0.6s.

### 3. How It Works (replaces Features)

**Layout:** `max-w-[960px]`, white canvas background.

**Section opener:** Left-aligned eyebrow «Как это работает» + h2 `sh-display-xl` «Три шага от видео до рекомендаций»

**3 steps:**
- Step 1 (dominant, full-width card): Upload video — accent: «Никаких специальных камер или настроек»
- Step 2 (paired left, wider): Get the breakdown — accent: «12+ параметров по каждому кадру»
- Step 3 (paired right, narrower): Compare to reference — accent: «Объективные данные для тренера и ученика»

**Structure:** Step 1 = `p-8 md:p-12`, horizontal layout (icon + text). Steps 2-3 = `md:grid-cols-[1.2fr_1fr]`. Watermark numbers (01, 02, 03). Icon circles with hover color flip.

**GSAP:** `ScrollTrigger` with `toggleActions: 'play none none none'`. Each step: `opacity: 0, y: 40 → opacity: 1, y: 0` with stagger 0.15s.

### 4. Demo Section (GSAP pinned scroll)

**KILLER FEATURE.** This is the product demo shown through scroll.

**Structure:**
- Container: `max-w-4xl`, `aspect-video`, centered
- Pin: `scrollTrigger: { pin: true, scrub: 1, end: '+=200%' }`
- 3 phases scrubbed by scroll position (0-33%, 33-66%, 66-100%):
  1. **Raw video** — stock skating image, no overlay
  2. **Skeleton overlay** — same image + SkeletonPose + dark overlay
  3. **Metrics HUD** — skeleton + 3 opaque metric badges (Высота ЦМТ, Доворот, Время полёта) + tech spec strip

**Below pinned area:** Text «Видео → Скелетон → Метрики за 12 секунд» as a pipeline explanation.

**Mobile:** No pin. Simple `whileInView` entrance animation via `gsap.matchMedia()`. 3 static phase cards stacked vertically (before/after style), each with the image at that phase.

**GSAP timeline:**
```
const mm = gsap.matchMedia()

mm.add("(min-width: 768px)", () => {
  // Desktop: pinned 3-phase scroll
  gsap.timeline({
    scrollTrigger: { trigger, pin: true, scrub: 1, end: '+=200%', anticipatePin: 1 }
  })
    .to(phase1Overlay, { opacity: 0, duration: 1 })
    .to(phase2Elements, { opacity: 1, duration: 1 }, 0.5)
    .to(phase3Badges, { opacity: 1, y: 0, duration: 0.5 }, 1.5)
})

mm.add("(max-width: 767px)", () => {
  // Mobile: simple entrance, no pin
  gsap.from(demoContainer, { opacity: 0, y: 30, duration: 0.6,
    scrollTrigger: { trigger: demoContainer, start: 'top 85%', toggleActions: 'play none none none' }
  })
})
```

Use `dvh` units for viewport height (`min-h-[100dvh]`) to avoid mobile address bar issues.

### 5. Trust Wall (Animated Counters)

**No placeholder testimonials.** Fake quotes damage credibility. Trust wall uses only animated counters until real testimonials available post-pilot.

**Animated counters:**
- «1,200+ сессий проанализировано»
- «340+ фигуристов»
- «15+ клубов»

**Layout:** `md:grid-cols-3`, centered. Each counter: large number (`sh-display-lg font-bold text-surface-violet-soft`) + label (`sh-caption text-ink-mute`).

**GSAP:** Counter animation with `gsap.to(target, { innerText: endValue, snap: { innerText: 1 }, duration: 2, scrollTrigger })`.

**Reduced motion:** Show final value immediately, no counting animation.

### 6. Pricing

**3 tiers** from unit-economics.md:

| Tier | Price | Segment | Included |
|------|-------|---------|----------|
| **Free** | 0 ₽/мес | Начинающие | 3 анализа/мес, базовый скелетон |
| **Pro** | 990 ₽/мес | Фигуристы | Безлимит анализов, рекомендации, прогресс, сравнение с эталоном |
| **Coach** | 3,500 ₽/мес | Тренеры | Dashboard учеников, диагностика, отчёты, до 20 учеников |

**Layout:** `md:grid-cols-3`, centered. Pro card slightly elevated (border highlight or `ring-2 ring-primary`). Each card: tier name, price, description, feature list (✓ check icons), CTA button.

**CTA copy:** Free → «Начать бесплатно», Pro → «Попробовать Pro» (`mailto:pro@skatelab.ru`), Coach → «Связаться с нами» (Telegram bot link `https://t.me/SkateLabBot`).

**Payment integration** (ЮKassa) is out of scope for this sprint. Pro and Coach CTAs link to contact channels until payment flow is implemented.

**GSAP:** Staggered scale-up entrance from `scale(0.95) opacity(0)`.

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

**Structure:** shadcn `Accordion`, `type="single" collapsible`. Max-width: `max-w-3xl`, centered.

**SEO:** JSON-LD `FAQPage` schema injected via `<script type="application/ld+json">`.

**GSAP:** Fade-up on scroll for the section header only. Accordion is interactive, no scroll animation needed.

### 8. CTA Section

**Structure:** Full-width teal band (`sh-teal-band`). Left-aligned text.

**Copy (from CustDev taglines):**
- Eyebrow: «Начните сегодня»
- H2: «Тренируй по данным, а не на ощущениях»
- Subtitle: «Первый анализ — бесплатно. Без подписки, без обязательств.»
- CTA: «Создать аккаунт» (on-teal button), «Уже есть аккаунт?» (ghost)

**GSAP:** Fade-up entrance.

### 9. Footer

**Structure:** `border-t border-hairline`, white/canvas background. `max-w-[960px]` container.

**Layout:** 4-column grid on desktop, stacked on mobile.

**Columns:**
1. **Brand:** SkateLab wordmark + tagline «Твой прыжок в цифрах»
2. **Product:** Как это работает / Тарифы / FAQ
3. **Legal:** Пользовательское соглашение / Оферта / Политика конфиденциальности / Cookie Policy
4. **Contact:** Telegram / VK icons + links

**Bottom bar:** `border-t` separator. `© 2026 SkateLab. Все права защищены.`

### 10. Cookie Banner

**Structure:** Fixed bottom bar, `z-50`. Shown only on first visit (localStorage flag).

**Content:** «Мы используем cookies для работы сервиса. Продолжая, вы соглашаетесь с Cookie Policy.»
**Action:** Button «Принять» → sets localStorage flag, hides banner. **Backend:** store consent in User table (`consent_accepted_at: timestamp`, `consent_categories: ["analytics"]`) via API call. localStorage is client-side only; DB record provides audit trail for 152-ФЗ compliance.

### 11. Legal Pages

| Route | Title | Content |
|-------|-------|---------|
| `/privacy` | Политика конфиденциальности | **Real content** (template from 152-ФЗ generator). Must exist before any user registration. |
| `/terms` | Пользовательское соглашение | Stub: «Документ готовится» + link back |
| `/offer` | Оферта | Stub: «Документ готовится» + link back |
| `/cookies` | Cookie Policy | Stub: «Документ готовится» + link back |

**Privacy Policy is mandatory** before collecting any personal data (152-ФЗ). Use a template service (e.g., document.ru, iubenda) or legal counsel. Other pages can remain stubs until payment integration.

### 12. Registration Consent Checkboxes

On `/register` page, add 2 separate checkboxes (required by 152-ФЗ since 2024):

1. «Я согласен на обработку персональных данных» → links to `/privacy`
2. «Я согласен на обработку анонимизированных данных (биометрия скелетона)» → links to `/privacy#anonymized`

Both required to submit registration form. Cannot be combined into one checkbox.

## GSAP Integration

### Dependencies

```bash
bun add gsap @gsap/react
```

### Architecture

- All GSAP code in `'use client'` components
- Register `ScrollTrigger` inside `useGSAP` or `useLayoutEffect`, never at module scope
- Use `gsap.matchMedia()` for all responsive behavior — never `window.matchMedia` directly
- `anticipatePin: 1` on all pinned ScrollTriggers for smoother pin transition
- Scope all animations to `useRef` containers
- `invalidateOnRefresh: true` on all ScrollTriggers for responsive
- `scrub: 1` (number) for smooth scroll-linked animations
- `ease: 'none'` for all scrub animations
- Kill all ScrollTriggers on page transition via `ScrollTrigger.killAll()`

### Animation Spec

| Section | Animation | Trigger | Duration |
|---------|-----------|---------|----------|
| Header | bg-color + blur transition | scroll past hero | scrub |
| Hero | staggered fade-up | page load | 0.8-1.2s each |
| How It Works | staggered fade-up cards | top 80% viewport | 0.5s each |
| Demo | pinned 3-phase timeline | scroll | scrub, end +=200% |
| Trust stats | counter animation | top 80% viewport | 2s |
| Pricing | scale-up stagger | top 85% viewport | 0.5s each |
| FAQ | header fade-up only | top 90% viewport | 0.6s |
| CTA | fade-up | top 85% viewport | 0.6s |

### Mobile Fallbacks

- Pinned demo → unpinned, 3 static phase cards
- Parallax → disabled (respects `prefers-reduced-motion`)
- Counter animations → show final value immediately if reduced-motion
- Staggered entrances → simultaneous if reduced-motion

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
- `landing.consent.*` (personalData, anonymizedData)

## Accessibility

- `aria-label` on all sections
- `aria-hidden="true"` on decorative SVGs (skeleton overlay, scroll arrow)
- Focus-visible on all interactive elements
- Skip-to-content link
- Cookie banner: `role="dialog"`, `aria-live="polite"`
- FAQ: proper accordion ARIA (controls, expanded states)
- Color contrast: all text meets WCAG AA (4.5:1 for body, 3:1 for large text)

## Performance Targets

| Metric | Target | Technique |
|--------|--------|-----------|
| LCP | < 2.5s | Preload hero image, fetchPriority="high" |
| CLS | < 0.1 | Explicit width/height on all images |
| INP | < 200ms | Defer GSAP init, use composited transforms only |
| JS bundle | < 150KB | Tree-shake GSAP, code-split heavy sections |

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
