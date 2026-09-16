# School Landing Pivot: implementation report

Date: 2026-09-16.
Status: implemented in the achievable repository scope; not approved for production launch.
Spec: [school landing pivot](../specs/2026-09-16-school-landing-pivot-design.md).

## Delivered

- Replaced the consumer-oriented public landing composition with a school-focused Arctic Sky page.
- Added a school-first hero, explicit development status, pilot CTA, review-example section, system workflow, coach/school scenarios, readiness matrix, FAQ and ocean closing band.
- Added a clearly labelled future-interface illustration instead of inventing a measured demo. No prices, accuracy numbers, testimonials, partner logos or efficacy claims remain in landing copy or metadata.
- Kept `/login`, legal links, existing app routes and the existing Telegram candidate contact. No backend, ML, mobile, payment or global design-system refactor was made.
- Added an interactive three-state example with explicit tabs and an accessible native FAQ disclosure. Added focused regression tests for the school CTA, removal of pricing copy and labelled illustrative fallback.
- Added consent-compatible PostHog event hooks using the existing `captureEvent` helper: `landing_pilot_intent`, `landing_demo_open`, and `landing_contact_click`, with only fixed location/type/tab properties.
- Updated Russian and English landing translations and metadata/FAQ JSON-LD.

## UI Skills evidence

The delegated worker environment did not expose the `functions.mcp` namespace, so it could not independently call `ui-skills_list_skills` or `ui-skills_get_skill`. The parent session previously verified the registry and router (`ibelick/ui-skills-root`) and specified the selected names in section 9.1. This report intentionally does not claim fresh MCP fetches by this worker. Parent must attach the actual MCP-fetched checklist and verify its applied decisions before accepting criterion 9.1.

Applied decisions from the existing specification/routing context:

- Landing composition: one school CTA, result-first sequence, large media area, editorial section rhythm, no pricing grid or repeated feature-card catalogue.
- Accessibility: 44px controls, semantic headings, native disclosure, tab roles, visible focus styles, keyboard-safe mobile dialog via FocusLock, no autoplay/audio requirement.
- Motion/performance: no new animation dependency or scroll interception; static content remains visible and media is below/alongside content with `next/image` sizing.
- Metadata: B2B title/description, no precision claims, no deleted testimonials/prices in FAQ JSON-LD.
- Critique/quality: Arctic Sky three-canvas rhythm, dark ink on sky hero, deep-ocean closing band, explicit prototype/illustration status and launch blockers.

### Parent-fetched MCP late pass

On 2026-09-16, after the original implementation was written, the parent session fetched and applied the actual MCP skill contents. This is a late corrective pass, not evidence that the delegated worker had MCP access or that the full upstream critique protocol ran:

- `mengto/landing-page`: kept one school offer, audience and primary pilot action; retained the proof-status section beside the illustrative demo and did not add unsupported testimonials or risk-reversal claims.
- `ibelick/fixing-accessibility`: corrected CTA analytics from pointer-only handlers to click handlers, added labelled tab panels with `aria-controls` / `aria-labelledby`, roving tab focus and ArrowLeft/ArrowRight/Home/End keyboard navigation, while retaining native links, disclosure and FocusLock Escape/return-focus behavior.
- `ibelick/fixing-metadata`: changed the OG image to an absolute URL and added matching `summary_large_image` Twitter metadata; canonical and OG URL remain `https://skatelab.ru`, and JSON-LD continues to reflect rendered FAQ content only.
- `pbakaus/critique`: retained school/trainer-specific language, the mobile fixed pilot action and explicitly labelled future-interface illustration; no two-agent critique fanout was run, so this is a degraded single-context application rather than a complete upstream critique run.
- `addyosmani/web-quality-audit`: checked source-level resource/semantic decisions and attempted live validation. No browser binary, Playwright package or Lighthouse/axe runner is installed in the available frontend environment; therefore no field or lab CWV, screenshot, console, Lighthouse or axe result is claimed.

The actual skill texts were fetched through MCP by the parent on this date; the worker's original environment exposed no MCP namespace. This report deliberately distinguishes applied source decisions from unperformed browser measurements.

## Human launch blockers

1. No verified, rights-cleared, reproducible single-attempt analysis is present in the repository. The current review panel is an honest illustration and does not satisfy the final evidence-demo criterion.
2. The Telegram URL exists in old code but responsible-person ownership and response workflow were not verified by this implementation. No public alternative email was available in repository evidence; do not publish a promise of response.
3. Sensor kit configuration, calibration, recording requirements and end-to-end sensor + video + coach review behavior need validation in a real practice.
4. Rights/consent for any future skater footage, especially minors, and the actual pilot data-access policy remain to be approved by the product owner.
5. Production browser screenshots, keyboard/reduced-motion/manual accessibility checks and laboratory performance measurements require a browser tool not available in this worker environment.

## Validation

- `cd frontend && bun run lint` passed.
- `cd frontend && bun run typecheck` passed.
- `cd frontend && bun run test --run src/components/landing/__tests__/landing-client.test.tsx` passed: 2 tests, including tab arrow-navigation assertions.
- `cd frontend && bun run test --run` passed: 57 files, 186 tests.
- `cd frontend && bun run lint` passed after the late corrective pass.
- `cd frontend && bun run typecheck` passed after the late corrective pass.
- `cd frontend && bun run build` failed at the unchanged baseline route graph: conflicting metadata for `/(blog)/[locale]/sitemap.ts` and `/(docs)/[locale]/sitemap.ts` at `/[locale]/sitemap.xml`. The original blog sitemap path is restored byte-for-byte; no temporary route rename remains in the diff. This blocker is outside landing scope and prevents meaningful production-build/browser validation.
- `bun run dev` + `curl http://localhost:3000/` was attempted with the restored baseline routes and returned HTTP 500 for the same sitemap collision. This is evidence of the baseline blocker, not a landing regression.
- Environment probes found no `node_modules/playwright`, browser binary, Lighthouse or axe runner; consequently no browser screenshot, keyboard/reduced-motion manual pass, console capture, axe/Lighthouse score, or lab CWV measurement is claimed.
- `git diff --check` passed.

No production deployment or third-party contact was performed.
