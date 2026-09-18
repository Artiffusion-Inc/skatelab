# Public navigation and phase selection

Verified locally on 2026-09-18; production release follows the website-only deployment procedure.

## Observed problem

At 390px and 1440px, clicking figure 02 on the homepage followed a single link
wrapping the entire diagram. It opened the process page at its introduction,
not the selected phase. The header had scrolled out of view. There was no
explicit home return, and the visitor lost their place.

## Decisions

- Reuse the phase explorer on the homepage. Each figure and its caption form
  one native button; selection updates the adjacent explanation, not the page.
- Keep the selected phase in the URL (`phase=1` through `phase=4`). Native
  `replaceState` integrates with Next's search parameters without adding a
  history entry or moving the viewport. Invalid values fall back to phase 1.
- Use a separate, named link to the process page's phase section, carrying the
  selection. Its home link returns to the homepage diagram with the same phase.
- Keep a solid, sticky header, existing current-page markers, and a visible
  home link on interior pages. Equipment and journal returns target their home
  sections. Use Next links for internal navigation and native history for Back.
- Offset anchor targets below the header. Keep keyboard focus, native button
  semantics, 44px minimum targets, and reduced-motion support. The existing
  pose emphasis now transitions in 180ms; no scroll hijacking or new library.

## Research

- [NN/g: Animation for Attention and Comprehension](https://www.nngroup.com/articles/animation-usability/):
  use motion to explain continuity and changes, not to delay navigation.
- [W3C: Consistent Navigation](https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation):
  preserve predictable placement and ordering across pages.
- UI Skills MCP: `vercel-labs-web-design-guidelines` and
  `wshobson-interaction-design`, consulted for navigation, feedback, and motion.
- Finding Skills search: [ux-navigation](https://github.com/parhamb/design-skills/blob/main/ux-navigation/SKILL.md),
  used as a secondary checklist. No skill or dependency installed: its useful
  guidance overlaps existing project skills. Repository scanner findings were
  manually checked; all six were lexical false positives in ordinary UX guidance
  or licensing text, not executable installation instructions.

## Checks and recovery

- Frontend unit regressions cover in-place selection, matching explanations,
  phase URL restoration/validation, explicit destination, and home return.
- Browser checks at 360, 390, 768, and 1440px cover figure hit areas, keyboard
  activation, unchanged scroll on selection, same-document navigation,
  browser Back restoring scroll and phase, direct entry, home anchors, menu
  dismissal, reduced motion, console errors, and horizontal overflow.
- Before release run all frontend tests, typecheck, lint, production build,
  and design-lock verification. Re-run browser checks against public HTTPS.
- Roll back only the website application to the previous verified frontend
  release (`e8aa3f4c`) through Dokploy if needed. Do not recreate backend workers
  or modify shared services/volumes. See [site deployment](site-deployment.md).
