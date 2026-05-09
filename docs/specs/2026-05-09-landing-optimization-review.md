# Landing Page Optimization Review

> Date: 2026-05-09
> Source: 5-agent parallel review (Animation, SSR, Asset, UX, Architecture)
> Scope: `frontend/src/components/landing/`, `frontend/src/app/(landing)/`, `frontend/src/app/globals.css`

## Executive Summary

- **LCP is broken** -- hero image (`/images/hero-skater.webp`) and OG image (`/images/og-image.png`) 404; `public/images/` directory does not exist. The `priority` preload is wasted on a 404.
- **~12-15KB gzipped Sentry SDK** statically imported in ErrorBoundary, shipped to every page bundle including landing. Dynamic import would be the single largest bundle win.
- **SkeletonPose burns CPU at 20fps even when off-screen** -- `setInterval(50ms)` with React `setState` causes ~60 re-renders/sec per instance. Two instances on the page (hero + demo). IntersectionObserver + rAF or CSS animation would save ~70% CPU.
- **`useAuth()` dead code on landing** -- hero, sticky-header, and cta-section all call `useAuth()`, triggering `fetchMe()` API call and re-render cascade. The server already redirects authenticated users via `cookies()` check in `page.tsx:34-35`.
- **Hero "Watch demo" link is broken** -- points to `#features` which has no matching section ID (the section uses `id="how-it-works"`).
- **Font loaded via CSS `@import`** (`@fontsource-variable/inter` in `globals.css:4`) instead of `next/font` -- no preload, no CLS override metrics, FOIT on slow connections, ~24KB unused greek/vietnamese subsets downloaded.
- **GSAP statically imported** (~25KB gz) in landing-client.tsx, skeleton-pose.tsx, trust-section.tsx, demo-section.tsx -- dynamic import would cut initial JS by ~35-40KB.

---

## P0 -- Must Fix (breaks functionality/LCP)

### P0-1. Missing image assets -- LCP broken, social previews broken

**Files:** `frontend/public/images/` (does not exist)
**References:** `hero-section.tsx:72` (`/images/hero-skater.webp`), `demo-section.tsx:100,168` (`/images/demo-skater.webp`), `page.tsx:23` (`/images/og-image.png`)

The `public/images/` directory does not exist. Hero image uses `priority` (preload hint) on a URL that 404s, wasting the preload and breaking LCP measurement. OG image 404 breaks social previews on Telegram/VK.

**Action:** Create `public/images/` and add the three required images. Verify with `curl -I https://skatelab.ru/images/hero-skater.webp` after deploy.

### P0-2. Hero "Watch demo" link broken

**File:** `hero-section.tsx:61`
```tsx
<a href={isAuthenticated ? "/progress" : "#features"}>
```

No element has `id="features"`. The HowItWorks section uses `id="how-it-works"` (`features-section.tsx:32`). Clicking "Watch demo" scrolls nowhere.

**Action:** Change `#features` to `#demo` (matches `demo-section.tsx:83`).

### P0-3. Cookie banner has no reject/close option -- GDPR risk

**File:** `cookie-banner.tsx:34-39`

Only an "Accept" button exists. Under GDPR (and Russian 152-FZ), users must be able to decline non-essential cookies. Currently the banner is dismissable only by accepting.

**Action:** Add a "Decline" button that sets `consent_accepted` to `"declined"` (or a separate key) and hides the banner. Update `landing-client.tsx:156-163` to handle both states.

---

## P1 -- High Impact (measurable perf/UX improvement)

### P1-1. Sentry SDK in every bundle (~12-15KB gzipped)

**File:** `error-boundary.tsx:1` (`import * as Sentry from "@sentry/nextjs"`)

Sentry is statically imported and thus included in every page chunk. The ErrorBoundary is a class component, so dynamic import requires wrapping or refactoring.

**Action:** Dynamic-import Sentry inside `componentDidCatch`:
```tsx
async componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
  const Sentry = await import("@sentry/nextjs")
  Sentry.captureException(error, { contexts: { react: { componentStack: errorInfo.componentStack } } })
}
```
This is safe because `componentDidCatch` is not on the render path. The static `import` at top can be removed entirely.

**Savings:** ~12-15KB gzipped from every page bundle.

### P1-2. Font via CSS `@import` instead of `next/font`

**File:** `globals.css:4` (`@import "@fontsource-variable/inter"`)

CSS `@import` blocks rendering, no `<link rel="preload">`, no CLS size-adjust override metrics, no font-display:swap, ~24KB of unused greek/vietnamese subsets downloaded.

**Action:** Remove `@import "@fontsource-variable/inter"` from `globals.css`. Add `next/font` in `layout.tsx`:
```tsx
import { Inter } from "next/font/google"
const inter = Inter({ subsets: ["cyrillic", "latin", "latin-ext"], variable: "--font-sans", display: "swap" })
```
Apply `inter.variable` on `<html>` or `<body>`. Update `globals.css:45,52` font-family stack to reference `var(--font-sans)`.

**Savings:** ~24KB unused font subsets eliminated, FOIT eliminated, CLS override metrics for stable layout.

### P1-3. GSAP statically imported (~25-40KB gzipped)

**Files:** `landing-client.tsx:5-6`, `demo-section.tsx:7-8`, `trust-section.tsx:5-6`, `skeleton-pose.tsx:7-8`

Four files statically import `gsap` and `ScrollTrigger`, shipping the full GSAP bundle to every landing page visitor.

**Action:** Dynamic-import GSAP in each file:
```tsx
const gsap = (await import("gsap")).default
const { ScrollTrigger } = await import("gsap/ScrollTrigger")
```
Since these are all inside `useLayoutEffect`/`useMountEffect`, the dynamic import works naturally. Move `gsap.registerPlugin(ScrollTrigger)` into the async effect. Centralize into a `useGSAP()` hook if desired.

**Savings:** ~35-40KB removed from initial bundle.

### P1-4. SkeletonPose 20fps React re-renders even when off-screen

**File:** `skeleton-pose.tsx:39-42`

Two instances (hero + demo) each run `setInterval(50ms)` calling `setFrame`, causing ~40 React re-renders/sec total. No visibility check -- runs at full speed even when scrolled past.

**Action:** Replace with IntersectionObserver + requestAnimationFrame + direct DOM mutation (bypass React):
```tsx
useLayoutEffect(() => {
  const svg = ref.current
  if (!svg) return
  let frame = 0, rafId: number, visible = false

  const observer = new IntersectionObserver(([e]) => { visible = e.isIntersecting }, { threshold: 0.1 })
  observer.observe(svg)

  const tick = () => {
    if (visible) {
      frame = (frame + 1) % 60
      // mutate SVG circles/lines directly
      svg.querySelectorAll("circle").forEach((c, i) => {
        const offset = Math.sin((frame + i * 10) * 0.1) * 0.015
        c.setAttribute("cx", String(BASE_POINTS[i].x + offset))
        c.setAttribute("cy", String(BASE_POINTS[i].y + offset * 0.5))
      })
      // similar for lines
    }
    rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
  return () => { cancelAnimationFrame(rafId); observer.disconnect() }
}, [])
```
Also respect `prefers-reduced-motion: reduce` -- skip animation entirely.

**Savings:** ~70% CPU reduction, eliminate React re-render overhead, pause when off-screen.

### P1-5. `useAuth()` dead code triggers API fetch on landing

**Files:** `hero-section.tsx:6,11`, `sticky-header.tsx:5,18`, `cta-section.tsx:5,9`

All three components call `useAuth()` which triggers `fetchMe()` on mount. The server already checks `sb_auth` cookie in `page.tsx:34-35` and redirects authenticated users to `/feed`. The `isAuthenticated` check in these components can never be true on the landing page (users would have been redirected away).

**Action:** Remove `useAuth()` import and usage from all three landing components. Remove `isAuthenticated` conditional branches. Simplify CTAs to always show unauthenticated paths (`/register`, `#demo`, `/login`).

**Savings:** Eliminates 1 unnecessary API call (`fetchMe`) + React context re-render cascade on every landing page load.

### P1-6. Hero entrance blocks first paint -- `gsap.set()` forces FOIC

**File:** `landing-client.tsx:38`

```tsx
gsap.set(heroEls, { opacity: 0, y: 20 })  // hides all hero elements
gsap.from(heroEls, { opacity: 0, y: 20, duration: 0.8, stagger: 0.12 })
```

`gsap.set()` immediately hides hero elements (opacity:0), creating a flash of invisible content (FOIC). CTA buttons are invisible for ~1.28s (5 elements * 0.12s stagger + 0.8s duration). `gsap.from()` already handles the initial state via `immediateRender:true` (default), making `gsap.set()` redundant.

**Action:** Remove `gsap.set(heroEls, { opacity: 0, y: 20 })` on line 38. Add `immediateRender: false` to `gsap.from()` if you want elements visible until the animation starts. Alternatively, set CSS `opacity: 0` on `.hero-eyebrow` etc. with a `gsap-active` class toggle to avoid FOIC.

**Savings:** CTA visible ~800ms sooner, no forced layout recalc.

### P1-7. CSS dead code -- three design systems, unused classes

**File:** `globals.css`

Three design systems coexist: `nike-*` (lines 261-286), `ice-*` (lines 176-248), `sh-*` (active). The `nike-*` classes (`nike-display`, `nike-h1`, `nike-h2`, `nike-h3`, `nike-body`) have zero usage in any component. `metric-giant` (line 235) and `sh-badge-flat` (line 370) also unused. `.dark` block (lines 135-173) ships dark-mode variables to a forced-light landing page.

**Action:**
1. Delete `nike-*` classes (lines 260-286) -- 26 lines
2. Delete `.metric-giant` (lines 235-240) -- 6 lines
3. Delete `.sh-badge-flat` (lines 370-373) -- 4 lines
4. Delete `ice-*` CSS variables and classes (lines 176-248) if not used by other routes (verify first)
5. Move `.dark` block to app-specific CSS or conditionally load

**Savings:** ~50-110 lines, ~3-4KB CSS.

### P1-8. Reduced motion incomplete -- `sh-metric-pulse` permanently dims, SkeletonPose unguarded

**Files:** `globals.css:390-396`, `skeleton-pose.tsx:39-42`

`globals.css:434-438` reduces animation/transition duration to 0.01ms, but `sh-metric-pulse` uses `@keyframes metricPulse` which gets the 0.01ms treatment, causing badges to freeze at 50% opacity (0.85) permanently. SkeletonPose ignores `prefers-reduced-motion` entirely.

**Action:**
1. Add `animation: none !important` override for `.sh-metric-pulse` under the reduced-motion media query in `globals.css`
2. Guard SkeletonPose animation with `matchMedia("(prefers-reduced-motion: reduce)")` check -- if true, render static SVG only

### P1-9. `react-focus-lock` in StickyHeader defeats CookieBanner dynamic import

**File:** `sticky-header.tsx:8`

FocusLock (~3KB gz) is statically imported in sticky-header.tsx, meaning it's in the initial bundle regardless of whether the mobile menu is ever opened. This also partially defeats the `dynamic()` import of CookieBanner since both share `react-focus-lock`.

**Action:** Dynamic-import FocusLock in sticky-header.tsx:
```tsx
const FocusLock = dynamic(() => import("react-focus-lock"), { ssr: false })
```
Or extract the mobile drawer into its own dynamically-imported component.

**Savings:** ~3KB gzipped from initial bundle.

### P1-10. Dynamic import below-fold sections -- ~30-40% initial JS reduction

**File:** `landing-client.tsx:7-14`

All 9 section components are statically imported and eagerly hydrated. Below-fold sections (Trust, Pricing, FAQ, CTA, Footer) add JS that the user won't see for seconds.

**Action:** Use `next/dynamic` for tier 2+ sections:
```tsx
// Tier 1: static (above fold + header)
import { HeroSection } from "./hero-section"
import { HowItWorksSection } from "./features-section"
import { StickyHeader } from "./sticky-header"

// Tier 2: dynamic with SSR (visible after 1 scroll)
const DemoSection = dynamic(() => import("./demo-section").then(m => ({ default: m.DemoSection })))
const TrustSection = dynamic(() => import("./trust-section").then(m => ({ default: m.TrustSection })))

// Tier 3: dynamic no-SSR (deep fold)
const PricingSection = dynamic(() => import("./pricing-section").then(m => ({ default: m.PricingSection })), { ssr: false })
const FAQSection = dynamic(() => import("./faq-section").then(m => ({ default: m.FAQSection })), { ssr: false })
```

**Savings:** ~30-40% initial JS reduction. Exact savings depend on per-component chunk sizes.

---

## P2 -- Medium Impact (quality and maintainability)

### P2-1. Demo phase buttons non-functional on desktop

**File:** `demo-section.tsx:155`

`onClick={() => setActivePhase(i)}` sets React state, but the demo animation is driven entirely by ScrollTrigger scrub. State changes have no visual effect on desktop. On mobile, the phases are static cards (no ScrollTrigger), so state is irrelevant.

**Action:** Add `scrollTo` on desktop: when a phase button is clicked, scroll to the corresponding progress point in the pinned section. Calculate target scroll position from the ScrollTrigger's progress (0.33, 0.66, 1.0).

### P2-2. Demo `setActivePhase` on every scroll tick

**File:** `demo-section.tsx:40-44`

```tsx
onUpdate: (self) => {
  const progress = self.progress
  if (progress < 0.33) setActivePhase(0)
  else if (progress < 0.66) setActivePhase(1)
  else setActivePhase(2)
}
```

`setActivePhase` is called on every scroll frame, even when the phase hasn't changed. React may bail out of re-renders if state is same, but the function call + comparison overhead still occurs ~60x/sec.

**Action:** Track previous phase and only call on change:
```tsx
let prevPhase = -1
onUpdate: (self) => {
  const phase = self.progress < 0.33 ? 0 : self.progress < 0.66 ? 1 : 2
  if (phase !== prevPhase) { setActivePhase(phase); prevPhase = phase }
}
```

### P2-3. Sequential awaits in page.tsx

**File:** `page.tsx:33-37`

```tsx
const hasAuth = (await cookies()).get("sb_auth")?.value
if (hasAuth) redirect("/feed")
const t = await getTranslations("landing")
```

`cookies()` and `getTranslations()` are independent. The redirect check must happen first, but if no redirect, both can run in parallel.

**Action:** If `hasAuth` is falsy, use `Promise.all` for the remaining independent awaits. Since the current code only needs `t` for FAQ items (which could be moved to the client), this is a minor improvement. Estimated savings: ~5-15ms.

### P2-4. All i18n messages shipped to all pages (~33KB ru.json)

**File:** `layout.tsx:28`

```tsx
<NextIntlClientProvider messages={messages}>
```

The root layout sends the entire `ru.json` (33KB, 650+ keys) to every page. The landing page only needs the `landing` namespace (~80 keys, ~3KB).

**Action:** Use `pick()` from `next-intl` to send only required namespaces:
```tsx
import { pick } from "next-intl/server"
const messages = await pick(await getMessages(), ["landing", "common"])
```
In the `(app)` route group layout, send the namespaces those pages need instead.

**Savings:** ~30KB less JSON sent to landing page clients.

### P2-5. Cookie banner `autoFocus` steals focus on page load

**File:** `cookie-banner.tsx:36`

`autoFocus` on the "Accept" button immediately steals focus from the page content when the banner renders. This is disorienting for screen reader users and keyboard navigators.

**Action:** Remove `autoFocus`. Add a 1.5s delay before focusing the banner dialog, so users can orient first. Use `useMountEffect` with `setTimeout`.

### P2-6. Mobile CTA bar CLS on cookie dismiss

**File:** `mobile-cta-bar.tsx:13-14`

When `hidden` is true, the component returns `null`, removing the element entirely. When cookie banner is dismissed, MobileCTABar appears and pushes content up by ~56px.

**Action:** Change from conditional rendering to `visibility: hidden` + `pointer-events: none` when hidden, preserving layout space. Or use `hidden` HTML attribute instead of returning null.

### P2-7. Header nav buttons lack focus-visible outlines

**File:** `sticky-header.tsx:71`

Nav buttons use `className="sh-body-md text-ink-mute hover:text-ink transition-colors"`. No `focus-visible:outline` or `focus-visible:ring`. Same issue in `features-section.tsx:69`, `demo-section.tsx:150`.

**Action:** Add `focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2` to all interactive buttons in header and section nav.

### P2-8. Skip-to-content link invisible on dark hero

**File:** `landing-client.tsx:170-173`

```tsx
className="... focus-visible:bg-primary focus-visible:text-primary-foreground"
```

The skip link uses `bg-primary` (oklch(0.145 0 0) -- near-black) on a `bg-primary` hero background. When focused, the link is invisible.

**Action:** Change `focus-visible:bg-primary` to `focus-visible:bg-surface-violet-soft` or `focus-visible:bg-white` to ensure contrast on the dark hero.

### P2-9. Pro/Coach CTAs link to Telegram with no fallback

**File:** `pricing-section.tsx:26-27,37`

Pro tier links to `https://t.me/SkateLabPro`, Coach to `https://t.me/SkateLabBot`. ~20-30% of the RU market does not have Telegram installed. Clicking these links opens a web page that prompts to install the app, creating a dead end.

**Action:** Add a fallback: if Telegram is not installed, open a contact form or email (`mailto:`). Detect with `setTimeout` + `document.hasFocus()` pattern, or provide a secondary CTA like "Email us".

### P2-10. Hardcoded Russian strings in aria-labels

**Files:** `demo-section.tsx:87,142`, `sticky-header.tsx:66,93,114,126`

Aria-labels like `aria-label="Фазы демо"`, `aria-label="Открыть меню"`, `aria-label="Основная навигация"` are hardcoded Russian strings. If i18n is extended to English, these won't switch.

**Action:** Replace with i18n keys: `t("demoPhaseAriaLabel")`, `t("headerMenuOpen")`, `t("headerNavAriaLabel")`. Add corresponding keys to `ru.json` and `en.json`.

### P2-11. No ErrorBoundary around GSAP sections

**File:** `landing-client.tsx`

If GSAP throws (e.g., ScrollTrigger init failure), the entire landing page crashes with a white screen. The `ErrorBoundary` exists (`error-boundary.tsx`) but is not wrapping landing content.

**Action:** Wrap the landing page content in ErrorBoundary:
```tsx
<ErrorBoundary>
  <div className="landing-page overflow-x-hidden" ref={containerRef}>
    ...
  </div>
</ErrorBoundary>
```

### P2-12. Trust section three separate ScrollTriggers

**File:** `trust-section.tsx:25-41`

Each counter creates its own ScrollTrigger instance with the same trigger and start position. A single timeline with staggered positioning would be more efficient.

**Action:** Use a single ScrollTrigger with a timeline:
```tsx
const tl = gsap.timeline({ scrollTrigger: { trigger: sectionRef.current, start: "top 80%", toggleActions: "play none none none" } })
countersRef.current.forEach((el, i) => {
  if (!el) return
  const obj = { val: 0 }
  tl.to(obj, { val: counters[i].target, duration: counters[i].duration, ease: "power2.out", onUpdate: () => {
    el.textContent = Math.round(obj.val).toLocaleString("ru-RU") + "+"
  }}, i * 0.2)
})
```

### P2-13. hero-cta class used on two different elements

**File:** `hero-section.tsx:37,46`

Both the stat line (`<div className="hero-cta mt-3">`) and the CTA buttons (`<div className="hero-cta mt-8">`) use the `hero-cta` class. GSAP's `querySelectorAll(".hero-cta")` in `landing-client.tsx:33` targets both, animating the stat line and buttons identically, which may cause the stat to appear before buttons finish staggering.

**Action:** Rename the stat line class to `hero-stat` and update GSAP selector in `landing-client.tsx:33`.

### P2-14. No mid-funnel CTA between demo and pricing

**File:** `landing-client.tsx:175-183`

The page flow is: Hero -> HowItWorks -> Trust -> Demo -> Pricing -> FAQ -> CTA -> Footer. After the demo (high engagement moment), users hit pricing (commitment moment) with no soft CTA in between.

**Action:** Add a "Try free analysis" micro-CTA after the demo section, linking to `/register`. This is a content/design decision, not a code bug.

### P2-15. Section narrative order interruption

**File:** `landing-client.tsx:177-179`

Trust section sits between HowItWorks and Demo, breaking the "how it works -> see it in action" narrative flow. Trust metrics (1200 sessions, 340 skaters) are more effective after the demo when the user has seen the product.

**Action:** Reorder: Hero -> HowItWorks -> Demo -> Trust -> Pricing -> FAQ -> CTA -> Footer.

### P2-16. Counter `onUpdate` not batched -- 180 extra DOM writes

**File:** `trust-section.tsx:37-39`

Each counter's `onUpdate` writes `textContent` on every GSAP tick (~60fps). With 3 counters running ~1s each, that's ~180 DOM writes. GSAP batches reads but not manual DOM writes.

**Action:** Throttle DOM writes with `requestAnimationFrame` or use GSAP's `snap`/`snap:endOnly` to reduce update frequency.

### P2-17. Demo pinned scroll jank on 60Hz

**File:** `demo-section.tsx:36`

`scrub: 1` means 1 second of smoothing. On 60Hz devices, this can feel laggy behind finger scroll.

**Action:** Increase to `scrub: 1.5` for smoother feel, or use `scrub: { value: 1.5, ease: "power1.out" }`.

---

## P3 -- Low Impact (hygiene and polish)

### P3-1. Duplicate i18n keys -- `feature*` and `howItWorks*`

**File:** `ru.json:88-99` and `ru.json:100-135`

The `feature*` keys (Upload/Metrics/Compare) are duplicated as `howItWorks*` keys with identical values. The `howItWorks*` variants are the active ones used in `features-section.tsx`. The `feature*` keys are dead.

**Action:** Delete keys `featuresTitle`, `featuresHeadline`, `featureUploadTitle`, `featureUploadDesc`, `featureUploadAccent`, `featureMetricsTitle`, `featureMetricsDesc`, `featureMetricsAccent`, `featureCompareTitle`, `featureCompareDesc`, `featureCompareAccent` (13 keys). Do the same in `en.json`.

### P3-2. Tier names in English for Russian UI

**File:** `ru.json:148,153,159`

`pricingFreeName: "Free"`, `pricingProName: "Pro"`, `pricingCoachName: "Coach"` are English words in the Russian translation file.

**Action:** Change to `"Бесплатный"`, `"Pro"` (keep Pro as brand name), `"Тренер"`.

### P3-3. "Dashboard учеников" mixes English/Russian

**File:** `ru.json:162`

`pricingCoachFeatures: "Dashboard учеников|Диагностика|Отчёты|До 20 учеников"`

**Action:** Change to `"Панель учеников|Диагностика|Отчёты|До 20 учеников"`.

### P3-4. "Увидьте миллиметры" -- archaic imperative

**File:** `ru.json:80`

`"Увидьте"` is archaic. Modern Russian uses `"Увидите"` (indicative future as imperative) or `"Замерьте"` (more precise for measurement context).

**Action:** Change `headlineLine2` to `"Замерьте миллиметры."` or `"Увидите миллиметры."`. Update `page.tsx:12,16` meta descriptions to match.

### P3-5. Legal pages use `<a>` instead of `<Link>`

**File:** `footer-section.tsx:48,52,56,60`, `legal-layout.tsx:8,11`

Legal page links (`/privacy`, `/terms`, `/offer`, `/cookies`) use `<a>` tags, causing full page reloads instead of client-side navigation.

**Action:** Replace `<a>` with `<Link>` from `next/link` for internal links in footer and legal-layout.

### P3-6. Redundant `role="contentinfo"` on footer

**File:** `footer-section.tsx:9`

`<footer role="contentinfo">` -- the `<footer>` element already has the `contentinfo` landmark role implicitly.

**Action:** Remove `role="contentinfo"`.

### P3-7. JSON-LD key uses array index

**File:** `page.tsx:76-82`

`jsonLd.map((schema, i) => <script key={i} .../> )` -- using array index as React key. While not a bug (schemas are static), using `schema["@type"]` is more semantic.

**Action:** Change `key={i}` to `key={schema["@type"]}`.

### P3-8. Three separate `gsap.registerPlugin()` calls

**Files:** `landing-client.tsx:21`, `demo-section.tsx:10`, `skeleton-pose.tsx:8`

`gsap.registerPlugin(ScrollTrigger)` is called three times. GSAP handles duplicate calls gracefully but it's code noise.

**Action:** Move to a single shared module or consolidate into `landing-client.tsx` only (since it loads first).

### P3-9. `gsap.set()` before `gsap.from()` in demo section

**File:** `demo-section.tsx:29-30`

```tsx
gsap.set(skeletonRef.current, { opacity: 0 })
gsap.set(badgesRef.current, { opacity: 0, y: 10 })
```

These `gsap.set()` calls are followed by timeline tweens that start at the same values. The sets cause an extra layout recalc. `gsap.from()` / timeline positioning handles initial state.

**Action:** Remove lines 29-30. Let the timeline tweens handle initial state via `from` or `fromTo`.

### P3-10. `invalidateOnRefresh: true` on demo ScrollTrigger unnecessary

**File:** `demo-section.tsx:39`

`invalidateOnRefresh` recalculates values on ScrollTrigger.refresh(). For a pinned section with fixed values, this causes unnecessary recalculation.

**Action:** Remove `invalidateOnRefresh: true` unless there's a specific dynamic resizing scenario.

### P3-11. Five separate `mm.add()` calls in landing-client.tsx

**File:** `landing-client.tsx:32-116`

Five `mm.add("(prefers-reduced-motion: no-preference)", ...)` calls create five separate matchMedia listeners. One call with all animations inside is cleaner.

**Action:** Consolidate into a single `mm.add()` callback containing all animation setup. Minor code clarity win.

### P3-12. Sticky header `backdrop-filter` inline style

**File:** `sticky-header.tsx:57`

```tsx
style={{ backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
```

**Action:** Move to a CSS class (e.g., `.header-blur { backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }`) for separation of concerns.

### P3-13. Pro tier badge overlaps on mobile

**File:** `pricing-section.tsx:68`

The `-top-3` positioning of the badge can overlap the ring border on narrow screens.

**Action:** Add `mt-6` to the Pro card on mobile, or use `@media (max-width: 1023px)` to position the badge differently.

### P3-14. No visual differentiation between internal/external CTAs

**Files:** `pricing-section.tsx:85-95`

Internal links (`/register`) and external links (`https://t.me/...`) look identical. Users don't know they're leaving the site.

**Action:** Add an external link icon (Lucide `ExternalLink`) or visual indicator for `target="_blank"` links.

### P3-15. `useEffect` convention violations in cookie check

**File:** `landing-client.tsx:155-158`

```tsx
useEffect(() => {
  const accepted = localStorage.getItem("consent_accepted")
  if (!accepted) setShowCookieBanner(true)
}, [])
```

Per project conventions, this should use `useMountEffect` or lazy state initialization. The current `useState(false)` + `useEffect` causes an extra render: false -> true.

**Action:** Use lazy state init: `const [showCookieBanner, setShowCookieBanner] = useState(() => typeof window !== "undefined" && !localStorage.getItem("consent_accepted"))`. Remove the useEffect.

### P3-16. Footer/Pricing could be server components

**Files:** `footer-section.tsx`, `pricing-section.tsx`

These sections have no client-side interactivity (no state, no effects, no event handlers beyond basic links). They could be server components, reducing client JS.

**Action:** Remove `"use client"`, replace `useTranslations` with `getTranslations` (server-side next-intl). Pass translated strings as props from `page.tsx`. Blocked by P1-5 (must remove `useAuth` dead code first for PricingSection).

### P3-17. Zero test coverage for landing

No test files exist for any landing component.

**Action:** Add smoke tests: render each section, verify key text content, check for broken links, verify CookieBanner accept flow. Use vitest + @testing-library/react.

---

## Implementation Waves

### Wave 1: Quick Fixes (1-2 hours, parallel)

All items are independent and can be done simultaneously.

| ID | Finding | Effort | File(s) |
|----|---------|--------|---------|
| P0-2 | Fix hero "Watch demo" link: `#features` -> `#demo` | S | `hero-section.tsx:61` |
| P1-5 | Remove `useAuth()` from hero, header, cta | S | `hero-section.tsx:6,11`, `sticky-header.tsx:5,18`, `cta-section.tsx:5,9` |
| P2-2 | Demo `setActivePhase` only on phase change | S | `demo-section.tsx:40-44` |
| P1-6 | Remove redundant `gsap.set()` in hero entrance | S | `landing-client.tsx:38` |
| P3-9 | Remove redundant `gsap.set()` in demo | S | `demo-section.tsx:29-30` |
| P3-8 | Consolidate `gsap.registerPlugin()` calls | S | `demo-section.tsx:10`, `skeleton-pose.tsx:8` |
| P2-8 | Fix skip-to-content link contrast | S | `landing-client.tsx:170` |
| P2-7 | Add focus-visible outlines to nav buttons | S | `sticky-header.tsx:71` |
| P3-6 | Remove redundant `role="contentinfo"` | XS | `footer-section.tsx:9` |
| P3-7 | Fix JSON-LD key to use `@type` | XS | `page.tsx:76` |
| P3-10 | Remove `invalidateOnRefresh` | XS | `demo-section.tsx:39` |
| P3-15 | Lazy state init for cookie banner | S | `landing-client.tsx:26,155-158` |
| P2-13 | Rename duplicate `hero-cta` class | S | `hero-section.tsx:37`, `landing-client.tsx:33` |

### Wave 2: Performance Core (4-6 hours)

| ID | Finding | Effort | Dependencies |
|----|---------|--------|--------------|
| P0-1 | Add missing image assets to `public/images/` | M | Design team provides images |
| P1-1 | Dynamic-import Sentry in ErrorBoundary | S | None |
| P1-2 | Switch to `next/font` with cyrillic+latin subsets | M | Remove `@fontsource-variable/inter` import |
| P1-3 | Dynamic-import GSAP in all landing components | M | Requires async useLayoutEffect refactor |
| P1-9 | Dynamic-import FocusLock in StickyHeader | S | None |
| P1-7 | Delete dead CSS (nike-*, metric-giant, sh-badge-flat) | S | Verify no usage in other routes |
| P1-8 | Fix reduced-motion for sh-metric-pulse + SkeletonPose | S | None |
| P2-4 | Use `pick()` for i18n namespaces | S | None |
| P2-3 | Parallel awaits in page.tsx | XS | None |
| P2-17 | Increase demo scrub to 1.5 | XS | None |

### Wave 3: Architecture (6-8 hours)

| ID | Finding | Effort | Dependencies |
|----|---------|--------|--------------|
| P1-4 | Replace SkeletonPose with IntersectionObserver + rAF + DOM mutation | M | Wave 2 (reduced-motion fix) |
| P1-10 | Dynamic import below-fold sections (Tier 2-4) | M | Wave 1 (remove useAuth), Wave 2 (GSAP dynamic import) |
| P0-3 | Add cookie banner reject option | M | P3-15 (lazy state) |
| P2-5 | Cookie banner: remove autoFocus, add delay | S | None |
| P2-6 | Mobile CTA bar: reserve space with visibility:hidden | S | None |
| P2-11 | Add ErrorBoundary around landing content | S | P1-1 (Sentry dynamic import) |
| P2-12 | Merge trust section ScrollTriggers into timeline | S | Wave 2 (GSAP dynamic import) |
| P2-16 | Batch counter DOM writes | S | P2-12 |
| P2-1 | Demo phase buttons: add scrollTo on click | M | Requires ScrollTrigger API |
| P2-10 | i18n for hardcoded aria-labels | S | Add i18n keys |
| P2-15 | Reorder sections: move Trust after Demo | S | None |
| P3-16 | Footer/Pricing as server components | M | Wave 1 (remove useAuth) |

### Wave 4: Polish (3-4 hours)

| ID | Finding | Effort | Dependencies |
|----|---------|--------|--------------|
| P3-1 | Delete duplicate i18n keys (feature* -> howItWorks*) | S | None |
| P3-2 | Tier names in Russian | XS | None |
| P3-3 | "Dashboard учеников" -> "Панель учеников" | XS | None |
| P3-4 | "Увидьте" -> "Замерьте" or "Увидите" | XS | Update meta descriptions in page.tsx too |
| P3-5 | Footer/legal `<a>` -> `<Link>` | S | None |
| P3-11 | Consolidate five `mm.add()` calls | S | None |
| P3-12 | Move backdrop-filter to CSS class | XS | None |
| P3-13 | Pro badge mobile overlap fix | XS | None |
| P3-14 | External link icon for Telegram CTAs | S | None |
| P2-9 | Telegram CTA fallback | M | Design decision needed |
| P2-14 | Mid-funnel CTA after demo | M | Design decision needed |
| P3-17 | Landing smoke tests | M | Wave 1-3 complete |

---

## Impact Projections

| Metric | Current (est.) | After Wave 2 | After Wave 3 |
|--------|---------------|-------------|-------------|
| Initial JS (gzipped) | ~180-200 KB | ~140-150 KB | ~110-120 KB |
| LCP | broken (404) | ~2.0s (fixed images) | ~1.5s (font preload + dynamic imports) |
| FCP | ~800ms | ~600ms (no GSAP FOIC) | ~500ms (dynamic imports) |
| CSS size (gzipped) | ~12-14 KB | ~8-10 KB (dead code removed) | ~8-10 KB |
| CPU (off-screen) | 40 re-renders/sec | 40 re-renders/sec | 0 (IObserver pausing) |
| API calls on load | 1 (fetchMe) | 0 | 0 |
| i18n JSON to client | ~33 KB | ~5 KB (pick landing) | ~5 KB |

Notes:
- Initial JS estimate assumes Next.js runtime (~80KB) + page chunks + component code + GSAP (~25KB gz) + Sentry (~12KB gz) + react-focus-lock (~3KB gz) + other deps.
- Wave 2 removes Sentry (12-15KB) + dead CSS (3-4KB) + font overhead.
- Wave 3 adds dynamic imports for below-fold sections (30-40% further reduction) + SkeletonPose rAF fix.
- LCP depends on image assets being provided (P0-1 is blocking).
- FCP improvement from removing `gsap.set()` FOIC and deferring GSAP to dynamic import.

---

## Appendix: Finding Cross-Reference

The following table maps each deduplicated finding to its original agent sources:

| Finding | Animation | SSR | Asset | UX | Architecture |
|---------|-----------|-----|-------|----|--------------|
| P0-1 Missing images | -- | #6 | #5 | -- | #4 |
| P0-2 Broken hero link | -- | -- | -- | #13 | -- |
| P0-3 Cookie no-reject | -- | -- | -- | #11 | -- |
| P1-1 Sentry SDK | -- | -- | #6 | -- | -- |
| P1-2 Font @import | -- | #5 | #4 | -- | -- |
| P1-3 GSAP static | -- | #4 | #1 | -- | -- |
| P1-4 SkeletonPose | #7,10 | #10 | -- | -- | #19 |
| P1-5 useAuth dead code | -- | #11 | -- | -- | -- |
| P1-6 Hero FOIC | #1,9 | -- | -- | -- | -- |
| P1-7 Dead CSS | -- | -- | #3 | -- | #3,20 |
| P1-8 Reduced motion | #10 | -- | -- | -- | -- |
| P1-9 FocusLock bundle | -- | -- | #2 | -- | -- |
| P1-10 Dynamic sections | -- | #3 | #10 | #1 | -- |
| P2-1 Demo buttons | -- | -- | -- | #4 | -- |
| P2-2 setActivePhase | #6 | -- | -- | -- | -- |
| P2-3 Sequential awaits | #1 | -- | -- | -- | -- |
| P2-4 Full i18n bundle | -- | #8 | -- | -- | -- |
| P2-5 autoFocus | -- | -- | -- | #2 | -- |
| P2-6 Mobile CTA CLS | -- | -- | -- | #3 | -- |
| P2-7 Focus-visible | -- | -- | -- | #12 | #10 |
| P2-8 Skip link contrast | -- | -- | -- | #10 | -- |
| P2-9 Telegram fallback | -- | -- | -- | #8 | -- |
| P2-10 Hardcoded aria | -- | -- | -- | -- | #5 |
| P2-11 ErrorBoundary | -- | -- | -- | -- | #8 |
| P2-12 Trust ST merge | #3 | -- | -- | -- | -- |
| P2-13 hero-cta class | -- | -- | -- | -- | #13 |
| P2-14 Mid-funnel CTA | -- | -- | -- | #15 | -- |
| P2-15 Section order | -- | -- | -- | #14 | -- |
| P2-16 Counter writes | #4 | -- | -- | -- | -- |
| P2-17 Demo scrub | -- | -- | -- | #5 | -- |
| P3-1 Duplicate i18n | -- | #7 | -- | -- | #2 |
| P3-2 Tier names RU | -- | -- | -- | #16 | -- |
| P3-3 Dashboard RU | -- | -- | -- | #17 | -- |
| P3-4 Archaic imperative | -- | -- | -- | #18 | -- |
| P3-5 <a> -> <Link> | -- | -- | -- | -- | #17 |
| P3-6 Redundant role | -- | -- | -- | -- | #12 |
| P3-7 JSON-LD key | -- | -- | -- | -- | #18 |
| P3-8 registerPlugin | #8,15 | -- | #1 | -- | #7 |
| P3-9 gsap.set before from | #9 | -- | -- | -- | -- |
| P3-10 invalidateOnRefresh | #12 | -- | -- | -- | -- |
| P3-11 mm.add consolidation | #11 | -- | -- | -- | -- |
| P3-12 backdrop-filter | -- | -- | -- | #6 | -- |
| P3-13 Badge overlap | -- | -- | -- | #7 | -- |
| P3-14 External link icon | -- | -- | -- | #9 | -- |
| P3-15 Lazy state init | -- | -- | -- | -- | #6 |
| P3-16 Server components | -- | #3 | -- | -- | -- |
| P3-17 Smoke tests | -- | -- | -- | -- | #16 |
