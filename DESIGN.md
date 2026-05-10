---
name: Skatelab Superhuman
description: AI-powered figure skating coach — Superhuman-inspired editorial precision with three-canvas color rhythm (indigo/white/teal), sub-default Inter Variable weights, and disciplined whitespace
colors:
  primary: "#1b1938"
  primary-deep: "#0e0c1f"
  on-primary: "#ffffff"
  ink: "#292827"
  ink-mute: "#73706d"
  ink-faint: "#9a9794"
  canvas: "#ffffff"
  canvas-soft: "#fafaf8"
  surface-violet-soft: "#c9b4fa"
  surface-teal-deep: "#0e3030"
  surface-teal-mid: "#155555"
  hairline: "#e8e4dd"
  hairline-dark: "#3f3a52"
  on-dark-mute: "#bcbac9"
  on-dark-dim: "#8a87a1"
  on-dark-faint: "#5a5772"
  destructive: "#c0392b"
  link: "#6c5ce7"
  ring: "#7c5ce7"
  score-good: "#27ae60"
  score-mid: "#f39c12"
  score-bad: "#e74c3c"
  accent-gold: "#f39c12"
typography:
  display-xxl:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "clamp(2.25rem, 5.5vw, 4rem)"
    fontWeight: 540
    lineHeight: 0.96
    letterSpacing: 0
  display-xl:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "clamp(2rem, 4vw, 3rem)"
    fontWeight: 460
    lineHeight: 0.96
    letterSpacing: "-1.32px"
  display-lg:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "28px"
    fontWeight: 540
    lineHeight: 1.14
    letterSpacing: "-0.63px"
  display-md:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 460
    lineHeight: 1.1
    letterSpacing: "-0.315px"
  heading-lg:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 460
    lineHeight: 1.2
    letterSpacing: "-0.4px"
  body-lg:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 540
    lineHeight: 1.5
    letterSpacing: "-0.135px"
  body-md:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 460
    lineHeight: 1.5
    letterSpacing: 0
  body-strong:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "18.72px"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: 0
  button-md:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.0
    letterSpacing: 0
  button-cap:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.0
    letterSpacing: 0
  caption:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 460
    lineHeight: 1.4
    letterSpacing: 0
  micro:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 540
    lineHeight: 1.4
    letterSpacing: 0
  legal:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 460
    lineHeight: 1.5
    letterSpacing: 0
  price:
    fontFamily: "'Inter Variable', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    fontSize: "clamp(2.25rem, 4vw, 3rem)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.03em"
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "16px"
  full: "9999px"
spacing:
  xxs: "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
  huge: "64px"
components:
  button-primary-dark:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  button-primary-dark-pressed:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  button-on-dark-pill:
    backgroundColor: "{colors.surface-violet-soft}"
    textColor: "{colors.primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
    padding: "12px 20px"
  button-secondary-outline:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.button-md}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  button-on-teal:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.surface-teal-deep}"
    typography: "{typography.button-md}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-mute}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  text-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
  card-feature-light:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    padding: "32px"
  card-teal-band:
    backgroundColor: "{colors.surface-teal-deep}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.lg}"
    padding: "64px"
  badge-opaque:
    backgroundColor: "oklch(0.175 0.066 315 / 0.85)"
    textColor: "{colors.on-primary}"
    typography: "{typography.micro}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  pill-tab-light:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.button-cap}"
    rounded: "{rounded.full}"
    padding: "8px 16px"
  nav-bar-dark:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.xs}"
    padding: "16px 24px"
  nav-bar-light:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.xs}"
    padding: "16px 24px"
  footer-light:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-mute}"
    typography: "{typography.caption}"
    rounded: "{rounded.xs}"
    padding: "64px 24px"
---

# Design System: Skatelab

## 1. Overview

**Creative North Star: "The Precision Instrument"**

A system inspired by Superhuman's editorial discipline: three-canvas color rhythm, sub-default typographic weights, and generous whitespace that makes every element earn its place. The aesthetic draws from figure skating's cold precision without falling into seasonal cliches. No snowflakes, no frosted borders, no winter pastels. Instead: indigo navy for authority, white canvas for clarity, deep teal for resolution.

The platform (dashboards, analytics, session reviews) dominates the register. The landing page opens with the indigo hero, resolves through white feature sections, and closes with the teal CTA band. The product inside is restrained, functional, and metric-forward.

**Key Characteristics:**
- Three-canvas system: indigo navy hero, white body, deep teal closing CTA
- Sub-default font weights (460, 540, 600) for typographic warmth signature
- Rounded-rectangle buttons (8px radius) everywhere except hero (pill-shaped)
- Warm ink (#292827, never pure black) on white canvas
- Hairline borders (1px, slightly warm grey) for separation
- Flat-By-Default elevation; shadows only on floating overlays
- Single CTA per section; nothing competing for attention
- Light-only theme (dark mode disabled until properly implemented)

## 2. Colors

Built on Superhuman's three-canvas polarity with figure skating's cold precision. All colors defined in OKLCH; hex values provided as sRGB approximations.

### Brand and Accent
- **Primary Indigo Navy** (#1b1938 / oklch(0.22 0.06 280)): The brand's primary surface and CTA color. Hero canvas, filled buttons, featured pricing tier, auth header.
- **Indigo Deep** (#0e0c1f / oklch(0.175 0.066 315)): Pressed-state lift, deeper navy for hero gradient stops.
- **Surface Violet Soft** (#c9b4fa / oklch(0.812 0.202 321)): The hero pill-button fill. Pale violet over the indigo canvas. Also in atmospheric backdrops and featured-card badges.
- **Surface Teal Deep** (#0e3030 / oklch(0.284 0.042 201)): The signature closing-CTA band color. Rich green-blue, almost black. Used only for the teal closing section.
- **Surface Teal Mid** (#155555 / oklch(0.41 0.068 201)): Slightly lifted teal for nested chrome inside the teal band.

### Surface
- **Canvas** (#ffffff / oklch(1 0 0)): Default body background. The white canvas between hero and teal closing.
- **Canvas Soft** (#fafaf8 / oklch(0.985 0.005 133)): Barely-warm off-white. Used for internal card bands only, never as a section background (violates Three-Canvas Rule).
- **Hairline** (#e8e4dd / oklch(0.92 0.018 118)): 1px borders, slightly warm grey.
- **Hairline Dark** (#3f3a52 / oklch(0.364 0.084 319)): 1px borders on dark surfaces and outline buttons.

### Text
- **Ink** (#292827 / oklch(0.278 0.003 106)): Default body text. Warm dark grey, never pure black.
- **Ink Mute** (#73706d / oklch(0.547 0.009 106)): Secondary text, captions, metadata.
- **Ink Faint** (#9a9794 / oklch(0.678 0.008 106)): Tertiary, disabled, placeholder text. Also used for decorative watermarks at low opacity.
- **On Primary** (#ffffff / oklch(1 0 0)): Text on dark navy / teal surfaces.
- **On Dark Mute** (#bcbac9 / oklch(0.795 0.042 316)): Secondary text on dark surfaces. Badge labels, supporting copy.
- **On Dark Dim** (#8a87a1 / oklch(0.63 0.04 317)): Intermediate dark-surface text. Used where On-Dark-Faint fails WCAG AA contrast on dark backgrounds (minimum 4.5:1 required). Badge labels that need more visibility than On-Dark-Mute provides less than.
- **On Dark Faint** (#5a5772 / oklch(0.47 0.087 317)): Tertiary text on dark. **WCAG WARNING:** Fails 4.5:1 contrast on badge-opaque backgrounds. Use On-Dark-Mute or On-Dark-Dim for any text below 18px / 14px bold.

### Semantic
- **Score Good** (#27ae60 / oklch(0.723 0.219 149)): Positive metric indicators. Always paired with checkmark or label.
- **Score Mid** (#f39c12 / oklch(0.795 0.184 86)): Warning metric range.
- **Score Bad** (#e74c3c / oklch(0.577 0.245 27)): Critical metric indicators. Always paired with icon or label.
- **Destructive** (#c0392b / oklch(0.541 0.22 25)): Errors, destructive actions.
- **Link** (#6c5ce7 / oklch(0.541 0.23 264)): Inline text links.
- **Ring** (#7c5ce7 / oklch(0.48 0.19 264)): Focus ring color.
- **Accent Gold** (#f39c12 / oklch(0.795 0.184 86)): Special highlights, PR indicators.

### Named Rules
**The Three-Canvas Rule.** Landing pages follow indigo hero, white body, teal closing. The teal band is non-negotiable on every marketing page. Adding a fourth canvas color (including canvas-soft as a section background) breaks the system. Canvas-soft is for internal card bands only.

**The No-Winter-Cliche Rule.** No snowflake icons, no frosted decorative borders, no frozen glass effects, no backdrop-filter blur on product screens. The cold identity is expressed through indigo hue and editorial precision, not literal winter imagery.

**The WCAG-Floor Rule.** On-Dark-Faint (oklch(0.47)) fails 4.5:1 contrast on dark surfaces. Any text below 18px / 14px bold on badge-opaque or primary backgrounds must use On-Dark-Mute or On-Dark-Dim instead. No exceptions.

## 3. Typography

**Font:** Inter Variable (with "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif fallback).

**Character:** A neutral-grotesque with technical precision. The brand uses sub-default variable weights (460, 540, 600) instead of standard 400/500/700. This quiet warmth in the typography distinguishes it from default SaaS systems.

### Hierarchy
| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| display-xxl | clamp(2.25rem, 5.5vw, 4rem) | 540 | 0.96 | 0 | Hero headline |
| display-xl | clamp(2rem, 4vw, 3rem) | 460 | 0.96 | -1.32px | Section opener on light |
| display-lg | 28px | 540 | 1.14 | -0.63px | Sub-section / closing CTA headline |
| display-md | 22px | 460 | 1.1 | -0.315px | Card title |
| heading-lg | 20px | 460 | 1.2 | -0.4px | Compact card title, FAQ question, auth heading |
| body-lg | 18px | 540 | 1.5 | -0.135px | Marketing body lead |
| body-md | 16px | 460 | 1.5 | 0 | Default UI body |
| body-strong | 18.72px | 700 | 1.5 | 0 | Emphasized body (weight 700) |
| button-md | 16px | 700 | 1.0 | 0 | Primary button label |
| button-cap | 14px | 600 | 1.0 | 0 | Compact button label, badge text |
| caption | 14px | 460 | 1.4 | 0 | Helper, footnote, metadata |
| micro | 12px | 540 | 1.4 | 0 | Pill label, fine print, eyebrow |
| legal | 11px | 460 | 1.5 | 0 | Copyright, terms |
| price | clamp(2.25rem, 4vw, 3rem) | 700 | 1 | -0.03em | Pricing display |

### Named Rules
**The Sub-Default Rule.** Use 460/540/600 instead of 400/500/700. The in-between weights are the brand's typographic warmth signature. Only body-strong (700) and button-md (700) exceed 600. No `font-semibold` (600) outside of button-cap and UI-interactive elements. No `font-medium` (500) anywhere; use 460 or 540.

**The Tight Display Rule.** 0.96 line-height on 48-64px display. Negative tracking tightens variable letterforms into editorial density.

**The 75ch Body Rule.** Body text lines must not exceed 75 characters. Use `max-w-[75ch]` on body containers, not arbitrary `max-w-lg` or `max-w-xl`. Scannability over density.

**The Token-Only Weight Rule.** All font weights must come through a design-system token class (`sh-display-xl`, `sh-body-md`, etc.). Never use raw Tailwind weight utilities (`font-medium`, `font-semibold`, `font-bold`) directly on text. If a component needs a specific weight, create or use the matching token class.

## 4. Elevation

Flat-By-Default. Surfaces are flat at rest. Depth via background color shifts (canvas, canvas-soft, card). Shadows only on floating overlays responding to interaction.

### Shadow Vocabulary
- **Ambient Low** (`box-shadow: 0 1px 3px rgba(0,0,0,0.08)`): Active tab, selected chip.
- **Ambient Medium** (`box-shadow: 0 4px 12px rgba(0,0,0,0.10)`): Dropdown menus, popovers.
- **Ambient High** (`box-shadow: 0 8px 24px rgba(0,0,0,0.12)`): Modals, floating toolbars.

### Atmospheric Depth
The hero's depth is the violet-sky atmospheric backdrop: a soft indigo-to-violet-to-sky-blue radial wash behind the portrait/abstract composition. Implemented as CSS radial gradient (`sh-violet-backdrop`). Below the hero, depth is minimal; the white canvas is flat.

### Named Rules
**The Flat-By-Default Rule.** No shadows on static cards, containers, or banners. Shadow appears only on floating overlays (dropdowns, modals, popovers) in response to interaction. Cookie banners, toast notifications anchored to the page: flat, not elevated.

**The No-Frosted-Glass Rule.** `backdrop-filter: blur()` is prohibited on headers, navs, and product surfaces. It violates the No-Winter-Cliche rule and degrades scroll performance. Use solid `bg-background` with opacity transition instead.

## 5. Components

### Buttons
- **Shape:** Rounded-rectangle (8px radius) everywhere except hero. The pill shape (9999px) only appears on the hero CTA.
- **Primary Dark:** Background Primary (#1b1938), text On-Primary (white), padding 12px 20px. Weight 700.
- **Primary Dark Pressed:** Background shifts to Primary-Deep (#0e0c1f). Active: scale(0.98).
- **On-Dark Pill:** Background Violet-Soft (#c9b4fa), text Primary. Pill shape. Hero only.
- **Secondary Outline:** Background Canvas, text Ink, 1px Hairline-Dark border.
- **On-Teal:** Background Canvas, text Teal-Deep. Rounded-rectangle. Inside closing teal band.
- **Ghost:** Transparent, no border. Hover: Canvas-Soft background.
- **Destructive:** Background Destructive/10, text Destructive. Hover: Destructive/20.
- **Active:** Scale 0.98 transform, no shadow. Sharp tactile feedback.
- **Hover:** translateY(-1px) for primary buttons. Color shift for ghost/outline.
- **Focus:** Border shifts to Ring, 2px ring in Ring/20. Transition 150ms.

### Cards / Containers
- **Corner Style:** 12px (lg) for feature and pricing cards. 8px (md) for inline containers, buttons, badges.
- **Background:** Canvas (white) or Canvas-Soft for alternating rows.
- **Shadow Strategy:** None at rest. Flat-By-Default.
- **Border:** 1px solid Hairline. Warm grey, not decorative.
- **Internal Padding:** 32px on pricing/feature cards, 24px on feature rows, 16px standard.

### Badge (Opaque)
- **Background:** oklch(0.175 0.066 315 / 0.85), 1px border oklch(0.812 0.202 321 / 0.4).
- **Text:** Primary-Foreground for values, On-Dark-Mute for labels. **Never On-Dark-Faint** (fails WCAG AA).
- **Radius:** 6px (md).

### Inputs / Fields
- **Style:** Background Canvas, 1px Hairline border, 6px (sm) radius. Padding 10px 12px.
- **Focus:** Border shifts to Primary, 2px ring in Ring/20.
- **Error:** Border Destructive, text Destructive.

### Navigation
- **App Nav (desktop):** Horizontal tabs, weight 460, 1rem size. Active tab: Muted background + Ink text. Hover: Canvas-Soft background.
- **Bottom Dock (mobile):** Fixed bottom bar, 1px Hairline border-top. 48px touch targets. Active: Ink text. Inactive: Ink-Mute.
- **Auth Nav:** Indigo navy background (nav-bar-dark). Logo in Violet-Soft.
- **Sticky Header (landing):** Solid bg-background, opacity 0-to-1 on scroll. No backdrop-blur. CTA button: variant="default" (primary dark).

### Signature Component: Teal Closing Band
Every landing page closes with a deep-teal CTA band. Contains a single display-lg headline and a button-on-teal. The teal is the page's resolving chord. Non-negotiable.

### Signature Component: Metric Card
Data-dense card for session list, progress dashboard, profile.
- Layout: metric label (caption) + score badge (right-aligned). Giant metric value (metric-giant scale) + sparkline or delta.
- Background: Canvas, 1px Hairline border.
- Score badge: Small pill, background Score-Good/Mid/Bad, white text. Always includes numeric score.

### Signature Component: Violet-Backdrop Hero
Hero section always uses `sh-violet-backdrop` (CSS radial gradient) over `bg-primary`. Single primary CTA (pill, on-dark-pill). No competing secondary CTA buttons; secondary actions are text links only.

## 6. Do's and Don'ts

### Do:
- Pair every hero with the violet-sky atmospheric backdrop.
- Render display tiers at sub-default weights (460/540). The warmth is the typographic signature.
- Use rounded-rectangle CTAs at 8px radius everywhere except hero (pill).
- Close every marketing page with a deep-teal CTA band.
- Use warm ink (#292827) for body text. Never pure black.
- Apply tight 0.96 line-height on display sizes.
- Pair score colors with icons or numeric labels for colorblind accessibility.
- Respect prefers-reduced-motion. Instant state changes, no bounce.
- Use `max-w-[75ch]` for body text containers.
- Use On-Dark-Mute or On-Dark-Dim for badge labels (WCAG AA compliance).
- Apply scale(0.98) on button active state for tactile feedback.

### Don't:
- Use pill-shaped buttons in the body of the page. The pill is hero-only.
- Bump display weight above 540 (except body-strong at 700).
- Render body text in pure black.
- Omit the closing teal band on marketing pages.
- Introduce accent colors beyond indigo, violet-soft, teal, and warm greys.
- Use shadow on static cards, containers, or banners. Flat-By-Default is absolute.
- Use border-left/right greater than 1px as a colored accent stripe.
- Use gradient text (background-clip: text). Single solid color. Emphasis via weight or size.
- Use glassmorphism, frosted glass, or backdrop-filter blur on product screens or navigation.
- Use the hero-metric template (big number + small label + gradient).
- Create identical card grids with icon + heading + text repeated endlessly.
- Use modals as a first solution. Exhaust inline progressive disclosure first.
- Use em dashes in copy. Use commas, colons, semicolons, or periods.
- Use canvas-soft as a section background. It breaks the Three-Canvas Rule.
- Use On-Dark-Faint for badge labels or any text below 18px on dark surfaces. It fails WCAG AA.
- Use raw Tailwind font-weight utilities (font-medium, font-semibold, font-bold) on text. Always use a design token class.
- Place two CTA buttons of equal visual weight in a single section. Secondary actions are text links.
