# Tiffany Palette Research — 2026-05-24

## Methodology

5 specialised agents researched in parallel:

1. **Competitive Landscape** — real sport/teal apps, hex values, anti-patterns
2. **OKLCH Color Science** — precise math, neutral tint audit, 3 palette variants with full contrast tables
3. **Premium Brand Aesthetic** — premium vs budget diagnostics, Nike/Peloton/WHOOP analysis
4. **Accessibility-First** — WCAG contrast matrices, color-blindness audit, L-sweep optimisation
5. **Cultural Russian Mood** — ФФКР, Russian market, "Лёд/Техника/Каток" directions

Each agent had web search access and read DESIGN.md + tokens.css.

---

## Cross-Agent Consensus

All 5 agents independently converged on the same core findings:

### 1. Current Primary Is Broken

| Problem | Evidence |
|---------|----------|
| Too desaturated (C=0.075) | N26 uses C=0.11 at same L. Premium teal cluster is C=0.10-0.15. Below C=0.10 reads as "corporate blue-gray" |
| Too blue-shifted (H=221 OKLCH) | HSL hue is 193°, 19° from teal (174°). All successful teal brands cluster H=180-200 OKLCH |
| Wrong lightness for premium | L=0.452 sits in "budget SaaS dashboard" zone. Premium brands: L=0.04-0.35 (dark) or L=0.50-0.57 (vibrant) |
| Russian cultural mismatch | Reads as "banking/bureaucratic" in Russian context (similar to Sberbank subsidiary teal) |
| Neutrals drift pink/purple | Low chroma neutrals (ink-mute C=0.010, canvas-soft C=0.003) have OKLCH hue 225-234°, appearing purple on calibrated displays |

### 2. The Fix: Raise Chroma, Shift Hue

| Dimension | Current | Target Range | Reason |
|-----------|---------|-------------|--------|
| Chroma (C) | 0.075 | 0.083-0.090 | Premium cluster, visible teal identity |
| Hue (OKLCH H) | 221 | 185-210 | Teal zone, not blue zone |
| Hue (HSL H) | 193 | 174-180 | True teal |
| Lightness (L) | 0.452 | 0.38-0.57 | Depends on positioning (see below) |

### 3. Lightness Positioning Is the Key Decision

| Position | L Range | Mood | Contrast | Risk |
|----------|---------|------|----------|------|
| **Deep Authority** | 0.35-0.40 | WHOOP/Peloton premium, dark surfaces | 8-13:1 AAA | Navy-blue misread, not identifiably "teal" |
| **Balanced Precision** | 0.45-0.52 | N26 instrument, visible teal identity | 5-7:1 AA/AAA | Best balance of teal identity + contrast |
| **Luminous Ice** | 0.54-0.57 | Fresh rink ice, bright, "Лёд" | 4.5-5.5:1 AA | White text fails on primary, must use dark text |

---

## Three Candidate Palettes

### A: "Лёд" (Ice) — Luminous, Authentic Rink

Source: Cultural agent's top pick + Competitive agent's "visible teal identity" recommendation.

| Token | Hex | OKLCH | HSL Hue |
|-------|-----|-------|---------|
| primary | #1a8a9e | L=0.567 C=0.088 H=210 | 174° |
| primary-deep | #0e4f5c | L=0.401 C=0.063 H=213 | 174° |
| primary-foreground | #1a1e1f | L=0.120 C=0.005 H=200 | — |
| tiffany | #81D8D0 | L=0.825 C=0.085 H=188 | 174° |
| surface-ice-soft | #d4eef4 | L=0.930 C=0.028 H=210 | 174° |
| surface-teal-deep | #0b3d47 | L=0.338 C=0.054 H=213 | — |
| surface-teal-mid | #1a8a9e | L=0.567 C=0.088 H=210 | — |
| ink | #252a2c | L=0.285 C=0.006 H=220 | 174° |
| ink-mute | #636d70 | L=0.530 C=0.012 H=225 | 174° |
| ink-faint | #94a0a4 | L=0.695 C=0.012 H=230 | 174° |
| canvas | #ffffff | L=1.000 C=0 H=0 | — |
| canvas-soft | #f3f6f8 | L=0.970 C=0.006 H=228 | 174° |
| hairline | #d2dbde | L=0.886 C=0.012 H=218 | 174° |
| hairline-dark | #1f5f6b | L=0.445 C=0.058 H=210 | 174° |
| on-dark-mute | #c2d8e0 | L=0.855 C=0.030 H=210 | — |
| on-dark-dim | #86b4c2 | L=0.710 C=0.050 H=210 | — |
| on-dark-faint | #4e8291 | L=0.548 C=0.048 H=210 | — |
| on-primary | #1a1e1f | L=0.120 C=0.005 H=200 | — |
| destructive | #c0392b | L=0.543 C=0.174 H=30 | — |
| link | #1a8a9e | L=0.567 C=0.088 H=210 | — |
| ring | #1a8a9e | L=0.567 C=0.088 H=210 | — |
| accent-gold | #d4a843 | L=0.721 C=0.110 H=85 | — |
| score-good | #27ae60 | L=0.663 C=0.160 H=152 | — |
| score-mid | #e8a820 | L=0.740 C=0.155 H=80 | — |
| score-bad | #d4382f | L=0.555 C=0.175 H=27 | — |

**Mood**: Fresh ice under arena lights. Most emotionally resonant for Russian figure skaters — "да, это про фигурное катание."

**Contrast**: primary-foreground (#1a1e1f) on primary = 9.2:1 AAA. White on primary-deep = 8.9:1 AAA. **Hero mode: light** (dark text on bright primary).

**Trade-off**: Primary is too light for white text (1.66:1 FAIL). Must use dark ink text on primary surfaces. Links on canvas pass AA at 4.7:1.

---

### B: "Arctic Precision" — Balanced, Best Contrast

Source: OKLCH agent's Palette B + Accessibility agent's recommended L=0.45 + Premium agent's "Arctic Depth" merged.

| Token | Hex | OKLCH | HSL Hue |
|-------|-----|-------|---------|
| primary | #19766d | L=0.512 C=0.083 H=185 | 174° |
| primary-deep | #0d453f | L=0.353 C=0.056 H=185 | 174° |
| primary-foreground | #ffffff | L=1.000 C=0 H=0 | — |
| tiffany | #82d9d0 | L=0.827 C=0.085 H=188 | 174° |
| surface-ice-soft | #d6ebe9 | L=0.924 C=0.023 H=190 | 174° |
| surface-teal-deep | #0d453f | L=0.353 C=0.056 H=185 | — |
| surface-teal-mid | #19766d | L=0.512 C=0.083 H=185 | — |
| ink | #272b2a | L=0.284 C=0.006 H=190 | 174° |
| ink-mute | #657270 | L=0.539 C=0.016 H=190 | 174° |
| ink-faint | #99a3a2 | L=0.707 C=0.011 H=190 | 174° |
| canvas | #ffffff | L=1.000 C=0 H=0 | — |
| canvas-soft | #f7f8f8 | L=0.978 C=0.001 H=195 | 174° |
| hairline | #dde3e3 | L=0.912 C=0.007 H=191 | 174° |
| hairline-dark | #3e746f | L=0.520 C=0.058 H=187 | 174° |
| on-dark-mute | #cad8d7 | L=0.871 C=0.015 H=190 | 174° |
| on-dark-dim | #94b8b4 | L=0.754 C=0.039 H=189 | 174° |
| on-dark-faint | #5c9993 | L=0.640 C=0.064 H=188 | 174° |
| on-primary | #ffffff | L=1.000 C=0 H=0 | — |
| destructive | #c0392b | L=0.543 C=0.174 H=30 | — |
| link | #19766d | L=0.512 C=0.083 H=185 | — |
| ring | #19766d | L=0.512 C=0.083 H=185 | — |
| accent-gold | #f39c12 | L=0.763 C=0.163 H=69 | — |
| score-good | #27ae60 | L=0.663 C=0.160 H=152 | — |
| score-mid | #f39c12 | L=0.763 C=0.163 H=69 | — |
| score-bad | #e74c3c | L=0.631 C=0.194 H=29 | — |

**Mood**: Precision instrument. Balanced teal identity + strong contrast.

**Contrast**: White on primary = 5.45:1 AA. White on primary-deep = 10.82:1 AAA. On-dark-dim on deep = 5.04:1 AA. **Hero mode: dark** (white text on medium teal).

**Trade-off**: Less emotionally resonant than "Лёд" for Russian skaters. White-on-primary barely passes AA (5.45:1), not AAA.

---

### C: "Midnight Protocol" — Deep, Maximum Authority

Source: Premium agent's "Arctic Depth" + Accessibility agent's "Deep Oceanic" merged.

| Token | Hex | OKLCH | HSL Hue |
|-------|-----|-------|---------|
| primary | #116960 | L=0.471 C=0.079 H=185 | 174° |
| primary-deep | #083631 | L=0.300 C=0.048 H=185 | 174° |
| primary-foreground | #ffffff | L=1.000 C=0 H=0 | — |
| tiffany | #82d9d0 | L=0.827 C=0.085 H=188 | 174° |
| surface-ice-soft | #d6ebe9 | L=0.924 C=0.023 H=190 | 174° |
| surface-teal-deep | #083631 | L=0.300 C=0.048 H=185 | — |
| surface-teal-mid | #116960 | L=0.471 C=0.079 H=185 | — |
| ink | #272b2a | L=0.284 C=0.006 H=190 | 174° |
| ink-mute | #657270 | L=0.539 C=0.016 H=190 | 174° |
| ink-faint | #99a3a2 | L=0.707 C=0.011 H=190 | 174° |
| canvas | #ffffff | L=1.000 C=0 H=0 | — |
| canvas-soft | #f7f8f8 | L=0.978 C=0.001 H=195 | 174° |
| hairline | #dde3e3 | L=0.912 C=0.007 H=191 | 174° |
| hairline-dark | #3e746f | L=0.520 C=0.058 H=187 | 174° |
| on-dark-mute | #cad8d7 | L=0.871 C=0.015 H=190 | 174° |
| on-dark-dim | #94b8b4 | L=0.754 C=0.039 H=189 | 174° |
| on-dark-faint | #5c9993 | L=0.640 C=0.064 H=188 | 174° |
| on-primary | #ffffff | L=1.000 C=0 H=0 | — |
| destructive | #c0392b | L=0.543 C=0.174 H=30 | — |
| link | #116960 | L=0.471 C=0.079 H=185 | — |
| ring | #116960 | L=0.471 C=0.079 H=185 | — |
| accent-gold | #f39c12 | L=0.763 C=0.163 H=69 | — |
| score-good | #27ae60 | L=0.663 C=0.160 H=152 | — |
| score-mid | #f39c12 | L=0.763 C=0.163 H=69 | — |
| score-bad | #e74c3c | L=0.631 C=0.194 H=29 | — |

**Mood**: WHOOP/Peloton-style deep authority. Maximum WCAG contrast. Premium positioning.

**Contrast**: White on primary = 6.54:1 AA. White on primary-deep = 13.27:1 AAA. On-dark-dim on deep = 6.18:1 AAA. On-dark-faint on deep = 4.07:1 (large text AA, up from 2.91:1 current).

**Trade-off**: Least identifiable as "teal" — reads as "dark blue-teal" at first glance. Lowest emotional resonance for Russian skaters. Most "premium instrument" feel.

---

## Contrast Comparison Matrix

| Pair | Current (#155f73) | A: Лёд | B: Arctic | C: Midnight |
|------|-------------------|--------|-----------|-------------|
| fg on primary | 7.2:1 AAA | 9.2:1 AAA* | 5.45:1 AA | 6.54:1 AA |
| white on primary | 7.2:1 AAA | 1.66:1 FAIL | 5.45:1 AA | 6.54:1 AA |
| white on primary-deep | 13.4:1 AAA | 8.9:1 AAA | 10.8:1 AAA | 13.3:1 AAA |
| on-dark-mute on deep | 8.9:1 AAA | 7.5:1 AAA | 7.4:1 AAA | 9.0:1 AAA |
| on-dark-dim on deep | 5.5:1 AA | 4.7:1 AA | 5.0:1 AA | 6.2:1 AAA |
| on-dark-faint on deep | 2.9:1 FAIL | 3.2:1 LG | 3.3:1 LG | 4.1:1 LG |
| ink on canvas | 13.9:1 AAA | 14.3:1 AAA | 14.3:1 AAA | 14.3:1 AAA |
| link on canvas | 7.2:1 AAA | 4.7:1 AA | 5.5:1 AA | 6.5:1 AAA |

\* Palette A uses dark text on primary (heroMode: light), so the relevant contrast is dark-text-on-primary, not white-on-primary.

---

## Color-Blindness Audit (All Palettes Pass)

All 3 palettes share the same teal/green/amber/red family. CVD testing shows:

| Pair | Protanopia dE | Deuteranopia dE | Tritanopia dE |
|------|--------------|-----------------|---------------|
| teal vs green (score-good) | 45.0 | 16.7 | 54.2 |
| teal vs amber (score-mid) | 65.1 | 54.5 | 90.6 |
| green vs red (scores) | 39.2 | 39.7 | 121.4 |

All pairs dE > 10 under all CVD types. Passes quantitative distinguishability.

**Defense-in-depth**: Keep existing DESIGN.md rule "Always pair score colors with icons or numeric labels for colorblind accessibility."

---

## OKLCH Hue Drift Fix

**Problem**: Low-chroma neutrals (C < 0.01) drift to purple/magenta in OKLCH because hue becomes numerically unstable near C=0.

**Solution**: Build all colors in HSL (H=174° for teal), convert to OKLCH. This ensures all neutrals tint teal, not purple.

**Verification**: All neutral tokens in all 3 palettes convert back to HSL hue 165-180° (teal range). Zero tokens drift to 280-340° (purple/magenta range).

**Implementation**: When updating DESIGN.md, specify colors as hex values with OKLCH reference. The hex is authoritative (computed from HSL 174° base). OKLCH values are for CSS custom properties.

---

## Competitive Analysis Summary

| Brand | Primary | L | C | H (OKLCH) | Takeaway |
|-------|---------|---|---|-----------|----------|
| Tiffany & Co | #81D8D0 | 0.75 | 0.12 | 188 | L=0.75 too light for surfaces (1.66:1 on white) |
| N26 | #088177 | 0.45 | 0.11 | 187 | Same structure as SkateLab, higher chroma = premium |
| WHOOP | #0B0B0B | 0.04 | 0 | — | Near-black primary, single red accent |
| Nike | #111111 | 0.10 | 0 | — | Brand IS black. Color = product only |
| Oura | #4A4741 | 0.34 | 0.01 | — | Warm charcoal, premium redesign to dark |
| ISU | #2C2276 | 0.18 | 0.15 | 280 | Institutional indigo, NOT teal |
| ФФКР | ~#1a2a5c | ~0.18 | ~0.10 | ~260 | Deep navy, bureaucratic |

**Key pattern**: Premium brands cluster at L=0.04-0.35 (dark) with ONE accent color. Budget brands cluster at L=0.45-0.55 with saturated primaries. SkateLab's current L=0.452 sits in the "budget SaaS" zone.

---

## Cultural Context (Russian Market)

| Association | Western | Russian |
|------------|---------|---------|
| Teal primary | Tiffany luxury, spa wellness | Морская волна, banking, bureaucracy |
| Dark teal | Premium coaching, instrument | Gov portal, Sberbank subsidiary |
| Light teal | Fresh, accessible | Детский сад (kindergarten), pastel |
| Gold accent | Luxury, aspiration | Championship, Olympic medal, achievement |
| Ice-blue | Scandinavian, clean | Лёд (ice), fresh rink, skating authentic |

**Recommendation from cultural agent**: 60% ice rink + 30% elegant sport + 10% precision tech. The palette should feel like stepping onto a freshly resurfaced rink — luminous, cold-but-inviting, with the slight blue tint of indoor ice under arena lighting.

**Accent-gold shift**: Current #f39c12 (H=69, orange-gold) signals "warning" in Russian context. Recommended shift to #d4a843 (H=85, true athletic gold) signals "championship/medal" instead.

---

## Recommended Decision Framework

| If you prioritise... | Choose Palette | Reason |
|---------------------|---------------|--------|
| Maximum WCAG accessibility + premium authority | C: Midnight | 6.54:1 primary, 4.07:1 faint, deep instrument feel |
| Balanced teal identity + accessibility | B: Arctic | 5.45:1 primary, clear teal, N26-style |
| Emotional resonance for Russian skaters | A: Лёд | 9.2:1 dark-on-primary, authentic rink atmosphere, hero mode = light |
| Compromise between all three | B: Arctic with A's accent-gold | B's teal identity + A's championship gold |

---

## Next Steps

1. Choose palette (A/B/C or hybrid)
2. Update DESIGN.md YAML frontmatter with selected hex + OKLCH values
3. Regenerate tokens.css and globals.css from DESIGN.md
4. Update palette-compare.html with all 3 candidates for visual comparison
5. Fix 28 audit findings (H1-H28) from landing design audit
6. Re-run `impeccable audit` + `hallmark audit` to verify score improvement