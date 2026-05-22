---
name: Skatelab Gentle Sea Breeze
description: AI-powered figure skating coach — Gentle Sea Breeze palette with three-canvas rhythm (teal-deep/white/surface-ice), sub-default Inter Variable weights, and disciplined whitespace
colors:
  primary: "#155f73"
  primary-deep: "#0e3340"
  primary-foreground: "#ffffff"
  ink: "#2a2d2e"
  ink-mute: "#6b7275"
  ink-faint: "#9ba0a3"
  canvas: "#ffffff"
  canvas-soft: "#f5f7f8"
  surface-ice-soft: "#c8e6f0"
  surface-teal-deep: "#0e3340"
  surface-teal-mid: "#155f73"
  hairline: "#d5dde0"
  hairline-dark: "#2a4a52"
  on-dark-mute: "#c5d5db"
  on-dark-dim: "#8aabb8"
  on-dark-faint: "#5a7a85"
  destructive: "#c0392b"
  link: "#155f73"
  ring: "#155f73"
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
    fontVariantNumeric: "tabular-nums"
rounded:
  xs: "4px"
  sm: "6px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  full: "9999px"
  2xl: "30px"
spacing:
  xxs: "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
  huge: "64px"
shadows:
  ambient-low: "0 1px 3px rgba(0,0,0,0.08)"
  ambient-medium: "0 4px 12px rgba(0,0,0,0.10)"
  ambient-high: "0 8px 24px rgba(0,0,0,0.12)"
components:
  button-primary-dark:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    typography: "{typography.button-md}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  button-primary-dark-pressed:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.primary-foreground}"
    typography: "{typography.button-md}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  button-on-dark-pill:
    backgroundColor: "{colors.surface-ice-soft}"
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
    textColor: "{colors.primary-foreground}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.lg}"
    padding: "64px"
  badge-opaque:
    backgroundColor: "oklch(0.301 0.047 225 / 0.85)"
    textColor: "{colors.primary-foreground}"
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
    textColor: "{colors.primary-foreground}"
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

**Creative North Star: "Gentle Sea Breeze"**

A cold, airy system inspired by the palette of sea ice and morning frost. The aesthetic draws from figure skating's cold precision without falling into seasonal cliches. No snowflakes, no frosted borders, no winter pastels. Instead: deep teal for authority and resolution, white canvas for clarity, ice-soft accents for atmosphere.

The platform (dashboards, analytics, session reviews) dominates the register. The landing page opens with a teal-deep hero, resolves through white feature sections, and closes with the teal CTA band. The product inside is restrained, functional, and metric-forward.

**Key Characteristics:**
- Three-canvas system: deep teal hero, white body, teal closing
- Sub-default font weights (460, 540, 600) for typographic warmth signature
- Rounded-rectangle buttons (12px radius) everywhere except hero (pill-shaped)
- Warm ink on white canvas
- Hairline borders (1px, slightly cool grey) for separation
- Flat-By-Default elevation; shadows only on floating overlays
- Single CTA per section; nothing competing for attention
- Light-only theme (dark mode disabled until properly implemented)

## 2. Colors

Built on a Gentle Sea Breeze polarity with figure skating's cold precision. All colors defined in OKLCH; hex values provided as sRGB approximations.

### Brand and Accent
- **Primary Teal** (#155f73 / oklch(0.452 0.075 221)): The brand's primary surface and CTA color. Hero canvas, filled buttons, featured pricing tier, auth header.
- **Teal Deep** (#0e3340 / oklch(0.301 0.047 225)): Pressed-state lift, deeper teal for hero gradient stops.
- **Surface Ice Soft** (#c8e6f0 / oklch(0.906 0.034 220)): Atmospheric backdrop accent. Pale ice-blue for hero atmospheric washes.
- **Surface Teal Deep** (#0e3340 / oklch(0.301 0.047 225)): The signature closing-CTA band color. Rich deep teal, almost black. Used only for the teal closing section.
- **Surface Teal Mid** (#155f73 / oklch(0.452 0.075 221)): Slightly lifted teal for nested chrome inside the teal band.

### Surface
- **Canvas** (#ffffff / oklch(1 0 0)): Default body background. The white canvas between hero and teal closing.
- **Canvas Soft** (#f5f7f8 / oklch(0.975 0.003 229)): Barely-cool off-white. Used for internal card bands only, never as a section background (violates Three-Canvas Rule).
- **Hairline** (#d5dde0 / oklch(0.892 0.010 222)): 1px borders, slightly cool grey.
- **Hairline Dark** (#2a4a52 / oklch(0.388 0.040 216)): 1px borders on dark surfaces and outline buttons.

### Text
- **Ink** (#2a2d2e / oklch(0.295 0.005 220)): Default body text. Warm dark grey with cool undertone, never pure black.
- **Ink Mute** (#6b7275 / oklch(0.547 0.010 225)): Secondary text, captions, metadata.
- **Ink Faint** (#9ba0a3 / oklch(0.703 0.007 234)): Tertiary, disabled, placeholder text. Also used for decorative watermarks at low opacity.
- **On Primary** (#ffffff / oklch(1 0 0)): Text on dark teal / teal surfaces.
- **On Dark Mute** (#c5d5db / oklch(0.863 0.019 222)): Secondary text on dark surfaces. Badge labels, supporting copy.
- **On Dark Dim** (#8aabb8 / oklch(0.721 0.041 224)): Intermediate dark-surface text. Used where On-Dark-Faint fails WCAG AA contrast on dark backgrounds (minimum 4.5:1 required).
- **On Dark Faint** (#5a7a85 / oklch(0.559 0.040 221)): Tertiary text on dark. **WCAG WARNING:** Fails 4.5:1 contrast on badge-opaque backgrounds. Use On-Dark-Mute or On-Dark-Dim for any text below 18px / 14px bold.

### Semantic
- **Score Good** (#27ae60 / oklch(0.663 0.160 152)): Positive metric indicators. Always paired with checkmark or label.
- **Score Mid** (#f39c12 / oklch(0.763 0.163 69)): Warning metric range.
- **Score Bad** (#e74c3c / oklch(0.631 0.194 29)): Critical metric indicators. Always paired with icon or label.
- **Destructive** (#c0392b / oklch(0.543 0.174 30)): Errors, destructive actions.
- **Link** (#155f73 / oklch(0.452 0.075 221)): Inline text links.
- **Ring** (#155f73 / oklch(0.452 0.075 221)): Focus ring color.
- **Accent Gold** (#f39c12 / oklch(0.763 0.163 69)): Special highlights, PR indicators.

### Named Rules
**The Three-Canvas Rule.** Landing pages follow teal-deep hero, white body, teal closing. The teal band is non-negotiable on every marketing page. Adding a fourth canvas color (including canvas-soft as a section background) breaks the system. Canvas-soft is for internal card bands only.

**The No-Winter-Cliche Rule.** No snowflake icons, no frosted decorative borders, no frozen glass effects, no backdrop-filter blur on product screens. The cold identity is expressed through teal hue and editorial precision, not literal winter imagery.

**The WCAG-Floor Rule.** On-Dark-Faint (oklch(0.559)) fails 4.5:1 contrast on dark surfaces. Any text below 18px / 14px bold on badge-opaque or primary backgrounds must use On-Dark-Mute or On-Dark-Dim instead. No exceptions.

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
The hero's depth is the ice-soft atmospheric backdrop: a soft teal-to-ice radial wash behind the composition. Implemented as CSS radial gradient (`sh-ice-backdrop`). Below the hero, depth is minimal; the white canvas is flat.

### Named Rules
**The Flat-By-Default Rule.** No shadows on static cards, containers, or banners. Shadow appears only on floating overlays (dropdowns, modals, popovers) in response to interaction. Cookie banners, toast notifications anchored to the page: flat, not elevated.

**The No-Frosted-Glass Rule.** `backdrop-filter: blur()` is prohibited on headers, navs, and product surfaces. It violates the No-Winter-Cliche rule and degrades scroll performance. Use solid `bg-background` with opacity transition instead.

## 5. Components

### Buttons
- **Shape:** Rounded-rectangle (12px radius) everywhere except hero. The pill shape (9999px) only appears on the hero CTA.
- **Primary Dark:** Background Primary (#155f73), text On-Primary (white), padding 12px 20px. Weight 700.
- **Primary Dark Pressed:** Background shifts to Primary-Deep (#0e3340). Active: scale(0.98).
- **On-Dark Pill:** Background Ice-Soft (#c8e6f0), text Primary. Pill shape. Hero only.
- **Secondary Outline:** Background Canvas, text Ink, 1px Hairline-Dark border.
- **On-Teal:** Background Canvas, text Teal-Deep. Rounded-rectangle. Inside closing teal band.
- **Ghost:** Transparent, no border. Hover: Canvas-Soft background.
- **Destructive:** Background Destructive/10, text Destructive. Hover: Destructive/20.
- **Active:** Scale 0.98 transform, no shadow. Sharp tactile feedback.
- **Hover:** translateY(-1px) for primary buttons. Color shift for ghost/outline.
- **Focus:** Border shifts to Ring, 2px ring in Ring/20. Transition 150ms.

### Cards / Containers
- **Corner Style:** 16px (lg) for feature and pricing cards. 12px (md) for inline containers, buttons, badges.
- **Background:** Canvas (white) or Canvas-Soft for alternating rows.
- **Shadow Strategy:** None at rest. Flat-By-Default.
- **Border:** 1px solid Hairline. Cool grey, not decorative.
- **Internal Padding:** 32px on pricing/feature cards, 24px on feature rows, 16px standard.

### Badge (Opaque)
- **Background:** oklch(0.301 0.047 225 / 0.85), 1px border oklch(0.906 0.034 220 / 0.4).
- **Text:** On-Primary for values, On-Dark-Mute for labels. **Never On-Dark-Faint** (fails WCAG AA).
- **Radius:** 12px (md).

### Inputs / Fields
- **Style:** Background Canvas, 1px Hairline border, 6px (sm) radius. Padding 10px 12px.
- **Focus:** Border shifts to Primary, 2px ring in Ring/20.
- **Error:** Border Destructive, text Destructive.

### Navigation
- **App Nav (desktop):** Horizontal tabs, weight 460, 1rem size. Active tab: Muted background + Ink text. Hover: Canvas-Soft background.
- **Bottom Dock (mobile):** Fixed bottom bar, 1px Hairline border-top. 48px touch targets. Active: Ink text. Inactive: Ink-Mute.
- **Auth Nav:** Teal-deep background (nav-bar-dark). Logo in Ice-Soft.
- **Sticky Header (landing):** Solid bg-background, opacity 0-to-1 on scroll. No backdrop-blur. CTA button: variant="default" (primary dark).

### Signature Component: Teal Closing Band
Every landing page closes with a deep-teal CTA band. Contains a single display-lg headline and a button-on-teal. The teal is the page's resolving chord. Non-negotiable.

### Signature Component: Metric Card
Data-dense card for session list, progress dashboard, profile.
- Layout: metric label (caption) + score badge (right-aligned). Giant metric value (metric-giant scale) + sparkline or delta.
- Background: Canvas, 1px Hairline border.
- Score badge: Small pill, background Score-Good/Mid/Bad, white text. Always includes numeric score.

### Signature Component: Ice-Backdrop Hero
Hero section uses `sh-ice-backdrop` (CSS radial gradient) over `bg-primary`. Single primary CTA (pill, on-dark-pill). No competing secondary CTA buttons; secondary actions are text links only.

## 6. Do's and Don'ts

### Do:
- Pair every hero with the ice-soft atmospheric backdrop.
- Render display tiers at sub-default weights (460/540). The warmth is the typographic signature.
- Use rounded-rectangle CTAs at 12px radius everywhere except hero (pill).
- Close every marketing page with a deep-teal CTA band.
- Use warm ink for body text. Never pure black.
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
- Introduce accent colors beyond teal, ice-soft, and warm greys.
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
