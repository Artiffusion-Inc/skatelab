---
name: Skatelab Arctic Sky
description: AI-powered figure skating coach — Arctic Sky palette with vibrant #29B6F6 blue-cyan primary, three-canvas rhythm (sky-bright/white/ocean-deep), sub-default Inter Variable weights, and disciplined whitespace
colors:
  primary: "#29B6F6"
  primary-deep: "#0A4D72"
  primary-foreground: "#0a1e2e"
  ink: "#0e1f2e"
  ink-mute: "#4A6E82"
  ink-faint: "#8BAAB8"
  canvas: "#ffffff"
  canvas-soft: "#EBF5FA"
  surface-ice-soft: "#D6EEF8"
  surface-teal-deep: "#0A4D72"
  surface-teal-mid: "#29B6F6"
  hairline: "#C8DDE8"
  hairline-dark: "#2E7EA0"
  on-dark-mute: "#D0E8F2"
  on-dark-dim: "#9AD0E4"
  on-dark-faint: "#68B8D0"
  destructive: "#D44444"
  link: "#1A7FA0"
  ring: "#29B6F6"
  score-good: "#4AAE68"
  score-mid: "#E0A830"
  score-bad: "#D04840"
  accent-gold: "#d4a843"
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

**Creative North Star: "Arctic Sky"**

A vibrant, airy system inspired by Arctic sky over fresh ice. The primary #29B6F6 is a confident blue-cyan — energetic and joyful without being pastel. Deep ocean-blue (#0A4D72) grounds the closing band and pressed states. All neutrals tint toward blue, never toward purple. The palette reads as "clean tech meets ice sport" — not banking, not kindergarten.

The landing page opens with a bright sky-blue hero (dark text, heroMode: light), resolves through white feature sections with ice-soft atmospheric accents, and closes with a deep ocean-blue CTA band. The product inside is restrained, functional, and metric-forward.

**Key Characteristics:**
- Three-canvas system: bright sky-blue hero (light mode), white body, deep ocean-blue closing
- Vibrant #29B6F6 primary — confident, not pastel
- Hero mode: light (dark text on bright primary, not white-on-dark)
- Sub-default font weights (460, 540, 600) for typographic warmth signature
- Rounded-rectangle buttons (12px radius) everywhere except hero (pill-shaped)
- Blue-tinted ink on white canvas, never pure black
- Hairline borders (1px, soft blue-grey) for separation
- Flat-By-Default elevation; shadows only on floating overlays
- Single CTA per section; nothing competing for attention
- Light-only theme (dark mode disabled until properly implemented)

## 2. Colors

Built on an Arctic Sky polarity with vibrant blue-cyan and ocean depth. All colors defined in OKLCH; hex values provided as sRGB approximations. All neutrals tint toward blue (OKLCH H=224-247), never toward purple.

### Brand and Accent
- **Primary Sky** (#29B6F6 / oklch(0.734 0.145 235)): The brand's vibrant primary surface and CTA color. Confident blue-cyan for hero canvas, filled buttons, featured pricing tier. HeroMode: light (dark text on bright surface).
- **Ocean Deep** (#0A4D72 / oklch(0.401 0.087 240)): Pressed-state lift, deep ocean-blue for closing band, gradient stops.
- **Tiffany** (#7DD3E8 / oklch(0.820 0.088 215)): Decorative pastel blue accent. Sparkle, not load-bearing.
- **Surface Ice Soft** (#D6EEF8 / oklch(0.935 0.029 225)): Atmospheric backdrop accent. Pale sky-blue for hero atmospheric washes.
- **Surface Teal Deep** (#0A4D72 / oklch(0.401 0.087 240)): The signature closing-CTA band color. Deep ocean-blue. Used only for the closing section.
- **Surface Teal Mid** (#29B6F6 / oklch(0.734 0.145 235)): = Primary. Slightly lifted for nested chrome inside the closing band.

### Surface
- **Canvas** (#ffffff / oklch(1 0 0)): Default body background. The white canvas between hero and closing band.
- **Canvas Soft** (#EBF5FA / oklch(0.964 0.013 229)): Barely-blue off-white. Used for internal card bands only, never as a section background (violates Three-Canvas Rule).
- **Hairline** (#C8DDE8 / oklch(0.885 0.027 230)): 1px borders, soft blue-grey.
- **Hairline Dark** (#2E7EA0 / oklch(0.560 0.092 230)): 1px borders on dark surfaces and outline buttons.

### Text
- **Ink** (#0e1f2e / oklch(0.233 0.037 247)): Default body text. Dark navy with blue undertone, never pure black.
- **Ink Mute** (#4A6E82 / oklch(0.519 0.052 233)): Secondary text, captions, metadata.
- **Ink Faint** (#8BAAB8 / oklch(0.719 0.040 227)): Tertiary, disabled, placeholder text.
- **On Primary** (#0a1e2e / oklch(0.227 0.041 245)): Text on bright primary. Dark navy, not white (heroMode: light).
- **On Dark Mute** (#D0E8F2 / oklch(0.916 0.029 225)): Secondary text on dark surfaces. Badge labels, supporting copy.
- **On Dark Dim** (#9AD0E4 / oklch(0.827 0.062 223)): Intermediate dark-surface text.
- **On Dark Faint** (#68B8D0 / oklch(0.740 0.086 219)): Tertiary text on dark. **WCAG WARNING:** Fails 4.5:1 contrast on badge-opaque backgrounds. Use On-Dark-Mute or On-Dark-Dim for any text below 18px / 14px bold.

### Semantic
- **Score Good** (#4AAE68 / oklch(0.674 0.139 151)): Positive metric indicators. Always paired with checkmark or label.
- **Score Mid** (#E0A830 / oklch(0.765 0.143 82)): Warning metric range.
- **Score Bad** (#D04840 / oklch(0.589 0.173 27)): Critical metric indicators. Always paired with icon or label.
- **Destructive** (#D44444 / oklch(0.592 0.181 25)): Errors, destructive actions.
- **Link** (#1A7FA0 / oklch(0.557 0.100 226)): Inline text links on white canvas. Darker than primary for AA contrast.
- **Ring** (#29B6F6 / oklch(0.734 0.145 235)): Focus ring color.
- **Accent Gold** (#d4a843 / oklch(0.753 0.127 85)): Championship gold, PR indicators. Athletic, not warning-orange.

### Named Rules
**The Three-Canvas Rule.** Landing pages follow bright sky-blue hero (heroMode: light), white body, deep ocean-blue closing. The closing band is non-negotiable on every marketing page. Adding a fourth canvas color (including canvas-soft as a section background) breaks the system. Canvas-soft is for internal card bands only.

**The No-Winter-Cliche Rule.** No snowflake icons, no frosted decorative borders, no frozen glass effects, no backdrop-filter blur on product screens. The cold identity is expressed through blue-cyan hue and editorial precision, not literal winter imagery.

**The WCAG-Floor Rule.** On-Dark-Faint (oklch(0.740)) fails 4.5:1 contrast on dark surfaces. Any text below 18px / 14px bold on badge-opaque or primary-deep backgrounds must use On-Dark-Mute or On-Dark-Dim instead. No exceptions.

**The Hero-Light Rule.** White text on primary (#29B6F6) fails WCAG AA (~2.3:1). Primary surfaces always use dark text (primary-foreground #0a1e2e, ~7.4:1 AAA). The closing band (primary-deep #0A4D72) uses white text (~9.1:1 AAA).

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
- **Primary Dark:** Background Primary (#29B6F6), text Primary-Foreground (#0a1e2e), padding 12px 20px. Weight 700. HeroMode: light.
- **Primary Dark Pressed:** Background shifts to Primary-Deep (#0A4D72), text White. Active: scale(0.98).
- **On-Dark Pill:** Background Ice-Soft (#D6EEF8), text Primary-Deep. Pill shape. Hero only.
- **Secondary Outline:** Background Canvas, text Ink, 1px Hairline-Dark border.
- **On-Teal:** Background Canvas, text Ocean-Deep. Rounded-rectangle. Inside closing ocean band.
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
- **Background:** oklch(0.401 0.087 240 / 0.85), 1px border oklch(0.935 0.029 225 / 0.4).
- **Text:** On-Primary for values, On-Dark-Mute for labels. **Never On-Dark-Faint** (fails WCAG AA).
- **Radius:** 12px (md).

### Inputs / Fields
- **Style:** Background Canvas, 1px Hairline border, 6px (sm) radius. Padding 10px 12px.
- **Focus:** Border shifts to Primary, 2px ring in Ring/20.
- **Error:** Border Destructive, text Destructive.

### Navigation
- **App Nav (desktop):** Horizontal tabs, weight 460, 1rem size. Active tab: Muted background + Ink text. Hover: Canvas-Soft background.
- **Bottom Dock (mobile):** Fixed bottom bar, 1px Hairline border-top. 48px touch targets. Active: Ink text. Inactive: Ink-Mute.
- **Auth Nav:** Ocean-deep background (nav-bar-dark). Logo in Ice-Soft.
- **Sticky Header (landing):** Solid bg-background, opacity 0-to-1 on scroll. No backdrop-blur. CTA button: variant="default" (primary dark).

### Signature Component: Ocean Closing Band
Every landing page closes with a deep ocean-blue CTA band. Contains a single display-lg headline and a button-on-teal. The ocean-blue is the page's resolving chord. Non-negotiable.

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
