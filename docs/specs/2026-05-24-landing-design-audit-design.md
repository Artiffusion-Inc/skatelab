# Landing Design Audit — 2026-05-24

## Methodology

1. **impeccable detect** (v2.1.9) — AI slop anti-pattern scanner → 0 findings on landing
2. **react-doctor** (v0.1.6) — React codebase health checker → 33 landing findings
3. **biome check** — lint/format → clean
4. **tsc --noEmit** — type check → clean
5. **Manual DESIGN.md rule cross-reference** — token consistency, rule violations
6. **design-lock.js check** — token drift detection
7. **hallmark audit** — structural slop detection, anti-pattern fingerprinting, design-system drift

---

## Audit Health Score (impeccable audit methodology)

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 2/4 | Content images empty alt, redundant role, autoFocus, wrong aria-labels |
| 2 | Performance | 3/4 | Hero Image missing `sizes`, GSAP ScrollTrigger properly gated by prefers-reduced-motion |
| 3 | Theming | 3/4 | Missing `sh-heading-md` token, opacity hack on dark text, token overrides |
| 4 | Responsive Design | 3/4 | Touch targets good (44px), padding inconsistent between sections |
| 5 | Anti-Patterns | 3/4 | Two equal-weight CTAs in hero, card grid pattern in features |
| 6 | Structural Slope (hallmark) | 1/4 | AI template fingerprint: centred hero, 3-col feature grid, 3-col step grid, AI footer |
| **Total** | | **15/24** | **Fair (structural + design-system fixes needed)** |

**Rating:** Good — a11y and theming need work, performance and responsive mostly fine.

---

## Tool Results

### impeccable detect — 0 anti-patterns on landing

No AI slop tells detected in landing components. Three findings outside landing scope:
- `video-with-skeleton.tsx:131` — `bg-black` (pure black)
- `verify-email-modal.tsx:39` — `bg-black` (pure black)
- `track-element.tsx:95` — `borderLeft: 3px solid` (side-tab)

### react-doctor — 33 landing findings

Grouped by rule:

| Rule | Count | Severity | Category |
|------|-------|----------|----------|
| `nextjs-no-a-element` | 16 | warning | Next.js |
| `design-no-redundant-size-axes` | 8 | warning | Architecture |
| `design-no-em-dash-in-jsx-text` | 4 | warning | Architecture |
| `no-redundant-roles` | 1 | warning | A11y |
| `no-autofocus` | 1 | warning | A11y |
| `no-danger` | 1 | warning | Correctness |
| `nextjs-image-missing-sizes` | 1 | warning | Next.js |
| `files` (knip dead code) | 1 | warning | Dead Code |

---

## Findings

### CRITICAL — Design System Violations

#### 1. `max-w-[65ch]` vs DESIGN.md 75ch Rule

**Rule:** "Body text lines must not exceed 75 characters. Use `max-w-[75ch]` on body containers."

**Reality:** Every body text container uses `max-w-[65ch]` — 22 instances across all landing sections. Consistently tighter than design spec.

**Verdict:** 65ch is better for Russian (longer words). **Decision needed:** update DESIGN.md to 65ch, or widen containers to 75ch. Both are valid within impeccable's "Cap body line length at 65–75ch" guidance.

#### 2. Missing `sh-heading-md` Token

`sh-heading-md` used in `sticky-header.tsx:61,118` but **not defined** in `globals.css`. Logo "SkateLab" renders without designed weight/tracking. Violates Token-Only Weight Rule.

**Fix:** Add to `globals.css`:
```css
.sh-heading-md {
  font-family: var(--font-sans);
  font-size: 18px;
  font-weight: 460;
  line-height: 1.3;
  letter-spacing: 0;
}
```

#### 3. `text-primary-foreground/70` — Opacity Hack

DESIGN.md defines `on-dark-mute` (oklch 0.863) and `on-dark-dim` (oklch 0.721) for dark surface text. `cta-section.tsx` uses `text-primary-foreground/70` (3 instances) instead:
- Different perceived color per background
- Violates "single solid color" rule
- Unpredictable WCAG contrast

**Fix:** Replace with `text-on-dark-dim` or `text-on-dark-mute`.

#### 4. `tracking-wider` / `tracking-widest` — Raw Tailwind Letter-Spacing

- `pricing-section.tsx:102` — `tracking-wider` on pricing badge
- `hero-section.tsx:78` — `tracking-widest` on scroll label

`sh-micro` defines `letterSpacing: 0`. These overrides contradict token. **Fix:** Remove, or define in token.

#### 5. `sh-badge-flat` Text Color Override

`hero-section.tsx:43` — `sh-badge-flat ... text-primary-foreground`. Token defines `color: var(--color-ink-mute)`. Override defeats token purpose.

**Fix:** Create `sh-badge-hero` token or use `sh-badge-opaque` for hero pills.

---

### HIGH — Accessibility (from react-doctor + manual)

#### 6. Content Images with Empty `alt=""`

**react-doctor:** silent (doesn't check alt semantics)
**Manual:** `visual-showcase-section.tsx`, `how-it-works-section.tsx` — all 6 content images have `alt=""`. Product screenshots with zero screen reader info.

**WCAG:** 1.1.1 Non-text Content (Level A) violation.

**Fix:** Add i18n alt text keys.

#### 7. Redundant `role="contentinfo"` on Footer

**react-doctor:** `footer-section.tsx:9` — `<footer role="contentinfo">` is redundant. `<footer>` has implicit `contentinfo` role.

**Fix:** Remove `role="contentinfo"`.

#### 8. `autoFocus` on Cookie Banner Accept Button

**react-doctor:** `cookie-banner.tsx:45` — `autoFocus` causes usability issues for sighted and non-sighted users. Can disorient screen reader users.

**Fix:** Remove `autoFocus`. FocusLock already traps focus; let the first focusable element receive focus naturally.

#### 9. Hero `aria-label` Uses Eyebrow Text

`hero-section.tsx:16` — `aria-label={t("eyebrow")}`. Eyebrow is marketing copy, not a section description. Screen readers announce "Фигурное катание 2.0" as the section identity.

**Fix:** Use dedicated aria key like `aria-label="Главный баннер"`.

#### 10. `MobileCTABar` `aria-label` Uses CTA Text

`mobile-cta-bar.tsx:17` — `aria-label={t("ctaPrimary")}`. Announces the button text, not the bar's purpose.

**Fix:** `aria-label="Панель действий"`.

---

### HIGH — Next.js Navigation (from react-doctor)

#### 11. `<a>` Instead of `next/link` — 16 Instances

**react-doctor:** `nextjs-no-a-element` — all internal links in landing use raw `<a>` instead of Next.js `<Link>`. Misses client-side navigation and prefetching.

Affected files: `sticky-header.tsx` (5), `footer-section.tsx` (4), `cookie-banner.tsx` (1), `cta-section.tsx` (1), `mobile-cta-bar.tsx` (1), `hero-section.tsx` (1), plus privacy/terms/offer/cookies pages (3).

**Note:** Some `<a>` tags are inside `asChild` on `<Button>`, which renders them as slots. The `asChild` pattern with Radix `Slot` means `<Link>` needs to be the `asChild` child instead of `<a>`.

**Fix:** Replace `<a href="/internal">` with `<Link href="/internal">` for all internal routes. Keep `<a>` for `#anchor` scroll links and external URLs.

---

### MEDIUM — Design Consistency

#### 12. Hero Has Two Equal-Weight CTAs

**Rule:** "Single CTA per section. Secondary actions are text links only."

`hero-section.tsx:50-68` — primary `variant="default"` + secondary `variant="outline"` — both full `<Button>`. Outline on dark hero is visually prominent.

**Fix:** Convert Telegram to text link (`text-on-dark-mute underline`).

#### 13. Inconsistent Section Padding

| Section | Mobile | Desktop | Pattern |
|---|---|---|---|
| Hero | `py-16` | `sm:py-20 lg:py-24` | spacious |
| Features | `py-20` | `md:py-28` | spacious |
| How It Works | `py-24` | `md:py-32` | very spacious |
| Accuracy | `py-20` | `md:py-28` | spacious |
| Visual Showcase | `py-16` | `md:py-24` | compact |
| Pricing | `py-16` | `md:py-24` | compact |
| FAQ | `py-16` | `md:py-24` | compact |
| CTA | `py-24` | `md:py-32` | very spacious |

No clear rhythm. **Suggestion:** Two patterns — spacious (hero/features/accuracy/CTA) and compact (visual/pricing/FAQ), with HowItWorks as the "hero of body sections" getting extra space.

#### 14. `sh-price` on Muted Text

`accuracy-section.tsx:38` — `sh-price text-ink-mute`. Large bold (700) with dim color — visual contradiction.

**Suggestion:** Add `sh-metric-value` token for large numeric values that aren't prices.

#### 15. `design-no-redundant-size-axes` — 8 Instances

**react-doctor:** Icon sizing uses `w-N h-N` instead of `size-N` shorthand.

Affected: `features-section.tsx` (2), `how-it-works-section.tsx` (2), `visual-showcase-section.tsx` (1), `pricing-section.tsx` (1), `sticky-header.tsx` (2).

**Fix:** Replace `w-N h-N` → `size-N` when both axes match.

---

### MEDIUM — Legal Pages (react-doctor)

#### 16. Em Dashes in Legal Pages

**react-doctor:** `design-no-em-dash-in-jsx-text` — 4 instances in `cookies/page.tsx` and `privacy/page.tsx`.

**DESIGN.md rule:** "No em dashes in copy. Use commas, colons, semicolons, or periods."

**Fix:** Replace `—` with appropriate punctuation.

---

### LOW — Minor Issues

#### 17. `dangerouslySetInnerHTML` in page.tsx

**react-doctor:** `(landing)/page.tsx:75` — JSON-LD structured data uses `dangerouslySetInnerHTML`. Biome already allows this with `biome-ignore` comment. Acceptable for SEO; no fix needed.

#### 18. Dead Code: `_FirstIcon` + `index.ts`

**react-doctor:** `how-it-works-section.tsx:58` — `const _FirstIcon = icons[0]` unused. `landing/index.ts` — unused file (no imports found).

**Fix:** Remove both.

#### 19. Token Overrides

- `hero-section.tsx:35` — `leading-relaxed` overrides `sh-body-lg` line-height (1.5 → 1.625)
- `hero-section.tsx:54,62` — `text-base` overrides `sh-button-cap` font-size (14px → 16px)
- `hero-section.tsx:54,62` — `h-14` (56px) vs `min-h-[44px]` pattern elsewhere

**Fix:** Remove overrides or update token definitions.

#### 20. Hero Image Missing `sizes`

**react-doctor:** `hero-section.tsx:20` — `next/image` with `fill` but no `sizes`. Browser downloads largest srcset. HowItWorks/VisualShowcase correctly have `sizes` — this one missed.

**Fix:** Add `sizes="100vw"` to hero background image.

---

## Anti-Patterns Verdict

**Pass.** Landing does NOT look AI-generated:
- No gradient text, glassmorphism, hero-metric template, or side-stripe borders
- Custom OKLCH color system, sub-default font weights (460/540), editorial typography
- Three-canvas rhythm (teal/white/teal) is intentional and branded
- One potential tell: feature card grid (icon + heading + text × 3) — but well-styled and differentiated enough to pass

---

## Positive Findings

- **Zero hardcoded colors** — all OKLCH via CSS custom properties
- **Consistent `sh-*` token usage** — 17 distinct token classes used
- **GSAP properly gated** — all animations respect `prefers-reduced-motion`
- **44px touch targets** everywhere — 26 instances of `min-h-[44px]`
- **Cookie banner flat** — no shadow (matches Flat-By-Default)
- **Sticky header solid bg** — no backdrop-blur (matches No-Frosted-Glass)
- **FocusLock** on mobile menu and cookie banner — proper a11y modal pattern
- **JSON-LD structured data** — FAQ + Organization + WebSite schemas
- **Skip-to-content link** — visible on focus

---

## Recommended Actions (Priority Order)

### P0 — Must Fix (design system integrity)
1. Define `sh-heading-md` in `globals.css` (Finding #2)
2. Replace `text-primary-foreground/70` → `text-on-dark-dim` (Finding #3)
3. Remove `tracking-wider`/`tracking-widest` (Finding #4)
4. Fix `sh-badge-flat` override → create `sh-badge-hero` or use `sh-badge-opaque` (Finding #5)

### P1 — Should Fix (accessibility + Next.js best practices)
5. Add meaningful `alt` text to 6 content images (Finding #6)
6. Remove `role="contentinfo"` from footer (Finding #7)
7. Remove `autoFocus` from cookie banner (Finding #8)
8. Fix hero and MobileCTABar `aria-label` (Findings #9, #10)
9. Replace `<a>` → `<Link>` for 12+ internal links (Finding #11)
10. Convert hero secondary CTA from button to text link (Finding #12)
11. Add `sizes` to hero background image (Finding #20)

### P2 — Nice to Fix (consistency + code quality)
12. Decide 65ch vs 75ch, update DESIGN.md (Finding #1)
13. Replace `w-N h-N` → `size-N` for 8 icon instances (Finding #15)
14. Remove dead code: `_FirstIcon`, `landing/index.ts` (Finding #18)
15. Remove em dashes from legal pages (Finding #16)
16. Fix token overrides: `leading-relaxed`, `text-base`, `h-14` (Finding #19)
17. Standardize section padding patterns (Finding #13)
18. Add `sh-metric-value` token (Finding #14)

### P1.5 — Hallmark Structural Findings (added 2026-05-24)

19. Break 3-equal-column feature grid pattern — `features-section.tsx`, `how-it-works-section.tsx` both use icon+heading+text × 3 equal columns. Vary widths, mix card heights, move icons inline, or use typographic rhythm instead of cards.
20. De-centre hero layout — `hero-section.tsx` uses `min-h-[100dvh]` with all content stacked centred. Bias layout left, remove full-viewport min-height.
21. Simplify footer — `footer-section.tsx` uses standard 4-column link grid (AI footer fingerprint). Switch to Ft1 Mast-headed or Ft5 Statement.
22. Rethink nav — `sticky-header.tsx` uses logo-left + 4 links + CTA-right (AI nav fingerprint). Consider N5 Floating pill or N8 Edge-aligned minimal.
23. Reduce scroll animations — only hero entrance should animate. Remove ScrollTrigger from Features, HowItWorks, Accuracy, Visual, Pricing, FAQ sections. One orchestrated entrance, then content just is.

Re-run `impeccable audit` + `hallmark audit` after fixes to see score improve from 15/24.

---

## Hallmark Audit — Detailed Findings

### CRITICAL (8)

| # | Tell | File | Fix |
|---|------|------|-----|
| H1 | 3-column feature grid | `features-section.tsx:41-62` | Break grid: vary widths, horizontal rows, typographic rhythm |
| H2 | Full-viewport centred hero | `hero-section.tsx:12-70` | Remove `min-h-[100dvh]`, bias left, asymmetric layout |
| H3 | AI footer | `footer-section.tsx:9-124` | Switch to Ft1 Mast-headed or Ft5 Statement |
| H4 | AI nav | `sticky-header.tsx:60-103` | Consider N5 Floating pill or N8 Edge-aligned minimal |
| H5 | Opacity hack tokens | `cta-section.tsx:13,17,33` | Replace `text-primary-foreground/70` → `text-on-dark-dim` |
| H6 | Tracking override | `hero-section.tsx:78` | Remove `tracking-widest` |
| H7 | Badge token override | `hero-section.tsx:43` | Replace `sh-badge-flat text-primary-foreground` → `sh-badge-hero` |
| H8 | Button height/font overrides | `hero-section.tsx:54,62` | Remove `h-14` and `text-base`, use `min-h-[44px]` only |

### MAJOR (15)

| # | Tell | File | Fix |
|---|------|------|-----|
| H9 | Animate-on-scroll on everything | `landing-client.tsx:56-207` | Keep hero entrance only, remove 6 other ScrollTrigger animations |
| H10 | Icon-tile feature card | `features-section.tsx:43-58` | Asymmetric layout, move icons inline |
| H11 | Icon-tile feature card | `how-it-works-section.tsx:73-95` | Remove icon squares, use step numbers as primary visual |
| H12 | Section padding inconsistency | Multiple | Apply 2-pattern system: spacious (py-20 md:py-28) and compact (py-16 md:py-24) |
| H13 | Two equal-weight CTAs in hero | `hero-section.tsx:50-68` | Convert Telegram to text link (`text-on-dark-mute underline`) |
| H14 | `sh-price` on muted text | `accuracy-section.tsx:38` | Use `sh-metric-value text-ink-mute` |
| H15 | `tracking-wider` on pricing badge | `pricing-section.tsx:102` | Remove `tracking-wider` |
| H16 | Content images empty alt | `visual-showcase-section.tsx`, `how-it-works-section.tsx` | Add i18n alt text keys |
| H17 | Redundant `role="contentinfo"` | `footer-section.tsx:9` | Remove `role="contentinfo"` |
| H18 | `autoFocus` on cookie banner | `cookie-banner.tsx:45` | Remove `autoFocus` |
| H19 | Wrong `aria-label` on hero | `hero-section.tsx:15` | Use `aria-label="Главный баннер"` |
| H20 | Wrong `aria-label` on MobileCTABar | `mobile-cta-bar.tsx:18` | Use `aria-label="Панель действий"` |
| H21 | `<a>` instead of `<Link>` | 12+ internal links | Replace with Next.js `<Link>` |
| H22 | Missing `sh-heading-md` in globals | `sticky-header.tsx:61,118` | **FIXED** — added to globals.css |
| H23 | Hero image missing `sizes` | `hero-section.tsx:20-27` | Add `sizes="100vw"` |

### MINOR (5)

| # | Tell | File | Fix |
|---|------|------|-----|
| H24 | Dead code `_FirstIcon` | `how-it-works-section.tsx:58` | Remove |
| H25 | Dead code `landing/index.ts` | Unused barrel file | Remove |
| H26 | `leading-relaxed` overriding token | `hero-section.tsx:35` | Remove or update token |
| H27 | `w-N h-N` instead of `size-N` | 8 instances | Replace with `size-N` shorthand |
| H28 | Em dashes in legal pages | `cookies/page.tsx`, `privacy/page.tsx` | Replace with punctuation |

---

### DESIGN.md Compliance Matrix

| Rule | Status | Notes |
|------|--------|-------|
| Three-Canvas Rule | PASS | teal hero → white body → teal closing |
| No-Winter-Cliche Rule | PASS | No snowflakes, frost, blur |
| WCAG-Floor Rule | FAIL | `text-primary-foreground/70` opacity hack |
| No-Opacity-Hack Rule | FAIL | 3 instances in CTA section |
| 65ch Body Rule | PASS | `max-w-[65ch]` throughout |
| Token-Only Weight Rule | FAIL | `text-base`, `h-14` overrides |
| No-Tracking-Override Rule | FAIL | `tracking-widest`, `tracking-wider` |
| Single CTA Rule | FAIL | Hero has 2 equal-weight buttons |
| Flat-By-Default Rule | PASS | No shadows on static cards |
| No-Frosted-Glass Rule | PASS | No backdrop-blur |
| Pill-Only-Hero Rule | PASS | Pill only on hero CTA |
| No-Side-Stripe Rule | PASS | No thick left/right borders |

Re-run `impeccable audit` after fixes to see score improve from 14/20.
