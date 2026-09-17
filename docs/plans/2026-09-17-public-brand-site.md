# SkateLab Public Brand Site Implementation Plan

**Goal:** Expand the approved landing into a coherent, detailed public website that a school can explore and the owner can share while building the mobile product and an audience.

**Execution:** Inline implementation authorized by the user; work on master, without worktrees. One repository writer. Separate media generation writes only temporary assets for integration.

**Architecture:** Extend the existing Next.js site and its bilingual MDX blog. Share the public navigation/footer and reuse campaign tokens. Use React state, SVG and CSS for explanatory scenes; use installed GSAP only where it materially improves motion. No new CMS, payment flow, account access or signup backend.

## Constraints And Decisions

- Preserve the approved cool-white/graphite/red campaign and existing hero, Edea-reference skate and coach imagery. Root Arctic Sky tokens remain product UI defaults, not the public campaign direction.
- Russian first; English parity through next-intl and bilingual MDX.
- Confirmed public contact: https://t.me/xpos587. No invented other social URLs; `/tiktok` can provide a useful link-in-bio destination without pretending to know the external account.
- Do not generate video. Two Higgsfield editorial stills are being produced in `/tmp/skatelab-site-media`; integrate after inspecting real files and provenance. Existing real-model skate-reference constraint continues.
- No development/synthetic-image badges in promotional sections. Use confident, accurate descriptions, not false availability, customer proof, performance results or endorsements. Interface and movement illustrations are educational examples, not a completed functioning app or measured athlete results.
- No invented reviews, dates, clients, payment methods, App Store links, hardware specifications or industrial-design registration numbers. Owner reports an industrial sample, but no verified photo/model was located; do not invent its appearance or turn that into a patent claim.
- Legal operator identity/country/email remain unresolved. Update Telegram references, preserve a concise factual draft notice where necessary; no claim of launch-ready legal compliance.
- No unauthorised production deployment or contact with third parties. Refresh local port 3000 after the final build.
- Native navigation and content work without JavaScript. Every interactive visual has usable default content, keyboard controls, >=44px targets, visible focus and reduced-motion support. No scroll hijacking or essential content opacity-gated on JS.

## Evidence And Reuse

- Browser-inspected reference: https://getcarv.com/ and https://getcarv.com/how-it-works. Temporary evidence `/tmp/skatelab-site-direction/` includes full-page captures and technical-selector interaction. Some homepage media did not load headlessly: no reference performance claim.
- Current active composition: `frontend/src/components/landing/landing-client.tsx`; older separate landing components are not the rendered homepage.
- Existing blog collection: `frontend/content/blog/{ru,en}/`; current route-group URLs and generated Fumadocs URLs disagree. Trace actual routing before integration, don't duplicate the content system.
- Existing metadata/sitemap: `frontend/src/app/sitemap.ts`, `frontend/src/lib/sitemap.ts`; preserve host-aware behavior while adding public-site routes/articles.
- Public provider guard: `frontend/src/lib/is-public-page.ts`; new marketing/blog routes must not invoke authenticated app fetching.
- Existing TikTok link-in-bio page currently sends visitors to disabled login/register. Replace with real marketing destinations.
- UI Skills MCP consulted: `leonxlnx/redesign-skill` for existing-stack layout/detail upgrades and `wshobson/interaction-design` for purposeful state transitions. Apply visual guidance, not suggestions to fabricate data or publication history. Local Impeccable brand and GSAP skills apply. Impeccable context script could not load its missing helper; PRODUCT/DESIGN read directly.

## Task 1 — A Connected Public Website

- [x] Add small regression checks for public route recognition, Telegram destinations, no login/promotional status badges and headline punctuation.
- [x] Extract only genuinely shared public chrome; add active navigation and responsive keyboard-accessible menu.
- [x] Build `/how-it-works`, `/equipment`, `/contact`, with a distinctive narrative and complete copy per page. Improve home with linked previews rather than duplicating subpages.
- [x] Activate real Telegram contact throughout live public routes, including legal contact references and link-in-bio. Manual enquiries/early interest go through Telegram; do not fake successful form signup.
- [x] Add useful FAQ details and coherent footer, legal links, cookie settings access, and branded missing-page recovery if needed.

## Task 2 — Detailed Visual Explanation And Editorial Content

- [x] Implement a phase explorer: preparation/takeoff/flight/landing controls change a skater/path SVG, annotation and explanation together. Not another tab strip that changes only text.
- [x] Implement a single tablet-like review composition with meaningful moment/context/next-task states, no fabricated metrics or athlete reports. On mobile the content stays readable instead of shrinking a desktop screenshot.
- [x] Equipment page pairs the skate photo with a camera/sensor explanatory diagram and an honest comparison of what each data source contributes. Do not fabricate a physical mounting product.
- [x] Add restrained motion that explains state, selected phase or spatial relationships. Default server content remains visible; reduced motion is immediate. No always-running ornamental loops.
- [x] Reuse MDX to ship a real blog index and article detail routes, with at least three useful substantial articles: filming a skating attempt, interpreting video vs sensor data, and structuring coach feedback. Real current dates, accurate content, useful headings and internal links. Rewrite misleading launch post claims rather than advertising unavailable features.
- [x] Integrate two new editorial Higgsfield stills and internal provenance, retain current hero/model-reference assets. Do not manufacture reviews or purchase/social badges merely to fill space.

## Task 3 — Delivery And Acceptance

- [x] Unique route/article metadata, canonicals, OG/Twitter previews and sitemap coverage. Validate article URL/locale correspondence, 404 handling and links on actual localhost production build.
- [x] Run `bun run test --run`, `bun run typecheck`, `bun run lint`, `bun run build` in frontend.
- [x] Production browser checks at 390, 768 and 1440px across public pages: no overflow/broken images/console errors; mobile nav, diagram controls, FAQ, cookie settings, article links and Telegram destination work. Check keyboard and reduced motion, no-JS main content, axe. Inspect screenshots rather than trusting assertions alone.
- [x] Measure/report performance honestly; prior mobile LCP exceeded 2.5s and is not a pass for this build. Avoid loading unnecessary 3D/video libraries into the hero.
- [x] Update a concise implementation report with evidence, image provenance, publication workflow and genuine remaining legal/social/hardware facts.
- [x] Parent final review, port 3000 refresh and exact-served-build verification; completed work included in the delivery commit. Review regression fixed with failing-then-passing test; final 203 tests and 57 core production browser cases pass.

## Checked Implementation

Worker implementation and standalone port 3300 verification completed 2026-09-17. Evidence, publishing workflow, image provenance, approved pre-existing docs routing/provider repairs, and honest mobile LCP limitation are recorded in `docs/reports/2026-09-17-public-brand-site-implementation.md`. Full frontend checks: 202 tests / 65 files, typecheck, lint and build passed. Browser: 57 public route/viewport cases plus 27 English cases; no remaining failures. Parent owns final review/commit/port 3000 refresh; no deployment.
