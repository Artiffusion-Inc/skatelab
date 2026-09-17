# Public Brand Site Implementation

**Date:** 2026-09-17. **Status:** Implemented, parent-reviewed and verified on local port 3000. No production deployment or third-party outreach. The parent generated two editorial stills; no video generation.

## Delivered Scope

- Connected home, `/how-it-works`, `/equipment`, `/contact`, `/blog/{ru,en}`, bilingual article detail pages, public `/tiktok`, legal shell and branded 404. The existing white/graphite/red campaign, Inter typography, hero, skate macro and coach image remain; `DESIGN.md` records the campaign exception to the application's Arctic Sky system.
- Shared public navigation with active states, a native mobile disclosure (including no-JavaScript operation and Escape), locale switching, footer, confirmed Telegram contact and cookie-settings access. Telegram destinations use `https://t.me/xpos587`; no other social account, download link, signup delivery, payment or hardware availability was invented.
- Four-phase movement explorer: selection changes the highlighted SVG pose, trace context, phase number and explanation. Review workspace: moment/context/next-attempt changes frame emphasis, annotation, phase strip and coach note. Equipment diagram: source selection changes the camera sightline versus inertial-signal emphasis and corresponding limitations. All have visible server defaults; phase/review/sensor explanatory alternatives remain available without JavaScript. These are explicitly instructional diagrams, not measurements, athlete reports or working app screenshots.
- Three substantive guides in each locale (recording, video versus sensors, coach feedback), plus an honest replacement for the tiny old launch announcement. Publication dates are 2026-09-17, the actual authoring date; the legacy announcement slug is retained for URL compatibility, not evidence of an earlier launch.
- Page/article canonicals, Open Graph/Twitter metadata, bilingual article alternates, root sitemap and robots rules. No unsupported product/review/offer schema.
- Public route guard now matches path boundaries, and AuthProvider avoids account fetching on marketing routes even when a stale session sentinel exists. Fixed the reproduced mobile cookie-button overflow; consent semantics and opt-in categories remain unchanged.

## Routing Corrections And Boundaries

Canonical editorial URLs are `/blog/ru/<slug>` and `/blog/en/<slug>`. `/blog` resolves from the selected locale. The old `/<locale>` and valid `/<locale>/<slug>` blog routes redirect; the actual `src/proxy.ts` handles old `/<locale>/blog/...` and `blog.skatelab.ru` URLs. Unknown locales/articles return 404. Locale-specific blog requests set a trusted request header after removing any incoming spoofed value, so document language, shell and article agree. Production CSP nonces are forwarded to the render request as well as returned in the response, allowing Next to nonce its scripts.

The old `src/app/middleware.ts` is not the Next.js entry point. It was not enabled or adopted as another middleware layer. New regression tests import the actual proxy.

Production inspection reproduced a pre-existing Fumadocs error: collections live in `content/{blog,docs}/{ru,en}` but the default parser is `dot`. This mixed languages, generated paths such as `/blog/ru/en/recording-guide`, and made documented page lookups fail. Shared `CONTENT_I18N` now uses `parser: "dir"` and no translation fallback. Blog has one shared loader. With parent approval, the same parser and existing `/<locale>/<slugs>` URL shape were applied to the three docs loaders and docs sitemap. An existing missing FrameworkProvider then caused docs HTTP 500; parent approved the minimal docs-only Fumadocs RootProvider, with nonexistent search disabled. Internal `requireStaff` and dynamic rendering remain unchanged. Public docs now return 200; unauthenticated internal docs return 307 without exposing article bodies. Internal pages remain excluded from sitemaps and robots. No docs redesign or new search API was introduced.

## Validation Evidence

Final source checks in `frontend/`:

| Command | Result |
| --- | --- |
| `bun run test --run` | Parent final run: 66 files, 203 tests passed |
| `bun run typecheck` | Passed, including Fumadocs generation |
| `bun run lint` | Parent final run: 281 files, no warnings/errors |
| `bun run build` | Passed, Next.js 16.2.4 production build |
| `git diff --check` | Passed |
| `git diff --cached --name-only` | Empty; no staged files |

Regression coverage added/updated: public-route boundaries and confirmed contact; actual proxy redirects/locale trust; public AuthProvider with stale session cookie; directory-based bilingual Fumadocs URL and lookup behavior; host-aware sitemap; homepage destinations/copy/headlines; phase, review and equipment selection. Failing-before-fix evidence is retained in `/tmp/skatelab-test-first.log`, `/tmp/skatelab-auth-test-first.log`, `/tmp/skatelab-proxy-test-first.log` and `/tmp/skatelab-loader-test-first.log`.

Production verification uses build ID `lHtOQ6TR8sfQMx0RlTHmT` on the standalone server at **127.0.0.1:3300**, with public/static assets copied to `.next/standalone/`. Parent owns port 3000; it was not restarted by this worker.

- `cd /tmp/skatelab-browser && node public-site.mjs`: **57 route/viewport cases**, 19 routes at **390, 768 and 1440px**; no failures. Loaded images were checked after actual viewport scrolling (instant automation scrolling avoids testing an unfinished smooth scroll). Zero horizontal overflow, page/console errors, or authenticated API calls on public routes, including with a stale `sb_auth` cookie. The 64 distinct discovered hrefs were checked without contacting Telegram or other third parties; local route destinations returned 200.
- Axe: **38 public route/viewport cases** (all 19 routes at 390 and 1440px), zero violations. The browser check also exercises navigation, native FAQ, mobile menu open/Escape, phase/review/sensor states, cookie reopen, canonical/OG presence, language switching, no-JavaScript content/contact/navigation, and reduced motion (computed diagram transition duration `0s`).
- `node english-and-details.mjs`: **27 additional English-cookie route/viewport cases**, all passed, including axe in those cases. Covers all non-blog public destinations at the three widths, document language and translated content, keyboard Enter/Tab/Escape, keyboard phase selection, cookie customisation/save, article anchors and a single-main branded 404.
- All root sitemap locations resolve, contain no duplicate locale segments or internal docs, and have no duplicate URLs. Docs-host sitemap uses the existing docs host and real docs paths. Blog unknown locale/missing article and unknown docs locale return 404; legacy blog redirects and internal-doc staff redirects were checked.
- Browser evidence: `/tmp/skatelab-public-site-check/report.json`, `/tmp/skatelab-public-site-check/english-and-details.json`; scripts: `/tmp/skatelab-browser/public-site.mjs`, `/tmp/skatelab-browser/english-and-details.mjs`. Earlier failures and corrected harness timing assumptions are not claimed as passes.

Screenshots were opened and visually inspected, not only generated: desktop process/equipment/contact, mobile home/process/legal, and tablet blog. Final captures include:

- `/tmp/skatelab-public-site-check/390-home.png`
- `/tmp/skatelab-public-site-check/390-how-it-works.png`
- `/tmp/skatelab-public-site-check/390-process-selected.png`
- `/tmp/skatelab-public-site-check/390-equipment-sensor.png`
- `/tmp/skatelab-public-site-check/768-blog-ru.png`
- `/tmp/skatelab-public-site-check/1440-equipment.png`
- `/tmp/skatelab-public-site-check/1440-contact.png`
- `/tmp/skatelab-public-site-check/1440-how-it-works.png`
- `/tmp/skatelab-public-site-check/390-en-home.png`
- `/tmp/skatelab-public-site-check/390-cookie-settings.png`
- `/tmp/skatelab-public-site-check/390-not-found.png`

## Performance: Not A Target Pass

`cd /tmp/skatelab-browser && node performance-public.mjs` runs installed Lighthouse 12.5.0 against the final production homepage, mobile simulated throttling, three runs. Results:

| Run | Performance | FCP | LCP | CLS | TBT |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.80 | 1.207s | 5.257s | 0 | 97ms |
| 2 | 0.83 | 1.205s | 4.505s | 0 | 110ms |
| 3 | 0.80 | 1.205s | 5.330s | 0 | 88ms |

The **2.5s mobile LCP target is not met**. This is laboratory data, not field/Core Web Vitals evidence or a product-performance claim. The hero is explicitly high-priority and remains the measured LCP candidate; this change does not eliminate simulated render delay. No video, WebGL or new animation dependency was added. Raw reports and environment/configuration: `/tmp/skatelab-public-site-check/lighthouse-{1,2,3}.json`, `performance.json`; console summary: `/tmp/skatelab-performance.log`. A broader provider/bundle performance optimisation is not smuggled into this campaign delivery.

## Media Provenance

Both new images were provided by the parent's Higgsfield generation task, decoded and visually inspected before integration. They are fictional editorial stills, not customer photographs, a device prototype, or actual app screens. No paid generation was invoked by this worker. Inputs/outputs and detailed prompts remain in `/tmp/skatelab-site-media/provenance.json`.

| Repository asset | Provider/model/job | Final file |
| --- | --- | --- |
| `frontend/public/images/landing/recording-guide.webp` | Higgsfield `gpt_image_2`, job `8a33591b-4152-4169-916c-30eb8447286e` | 1920x1080, 100264 bytes, SHA256 `63b89e38610f6c697ce966c7263e4ed7f4fcce5d6e0ceeda791208db62da874c` |
| `frontend/public/images/landing/training-notes.webp` | Higgsfield `gpt_image_2`, job `7d33d4e7-9c51-4f2f-bee2-56dbb6d12626` | 1920x1080, 138554 bytes, SHA256 `17c2110a69765c79c5d02dd5c583eaf0ab10bb9dbc57a2c6800c660d92d40799` |

Recording guide: coach with a handheld horizontal phone, unobstructed adult skater, existing campaign rink palette. The official Edea Ice Fly boot reference was used; blades are separate components, and fine mesh/construction fidelity is not verifiable at scene scale. This is not manufacturer endorsement or product certification. References: `https://edeaskates.com/en-us/ice-fly/` and `https://edeaskates.com/wp-content/uploads/2020/04/ice-fly-edea-skates.jpg`.

Training notes: blank notebook, pencil, gloves and powered-off tablet; no generated UI, personal notes or customer data. Both were exported as WebP quality 88 using Pillow, 16:9. Recording-image crops preserve the complete scene in the new recording chapters and journal lead. Existing hero/macro/coach provenance and rights limitations remain documented in `docs/reports/2026-09-16-school-landing-pivot-implementation.md`. No sensor product image was created.

## Publishing Workflow

1. Add paired `frontend/content/blog/ru/<slug>.mdx` and `frontend/content/blog/en/<slug>.mdx`. Keep matching ASCII slugs. Required validated frontmatter: `title`, `description`, actual `date` as quoted `YYYY-MM-DD`, and `image` from the schema's existing editorial-image enum in `frontend/source.config.ts`.
2. Start article body at `##`; the route owns the one H1, description, date, hero and heading-based contents navigation. Write substantive sourced/verified guidance. Distinguish observations, calculated estimates and coaching decisions. Do not invent launch dates, performance evidence, specifications, customers or endorsements.
3. Link articles as `/blog/ru/<slug>` or `/blog/en/<slug>` in matching-language MDX. Public process/equipment/contact links use their existing root paths. No manual CMS, sitemap entry or duplicate article template is needed; the shared loader and metadata routes discover the file.
4. For a new image, place the optimised file in `frontend/public/images/landing/`, extend the explicit schema enum, add accurate bilingual alt text/route mapping, and record provenance/rights review in a durable report. Do not label a generated representation as a verified device photo.
5. Run the four frontend checks. Verify both article URLs, language/metadata, TOC anchors, image, internal links and 404 behavior on a fresh production server at mobile and desktop widths. Review the draft legal notice before any public launch. Publication to production still requires an authorised deployment; this task did not deploy.

## Remaining Facts / Release Risks

- Legal operator identity/status, country, governing law, public email, provider/deployment details, retention and data-request process are not confirmed. Legal pages deliberately remain drafts; the verified Telegram does not resolve legal compliance.
- There is no confirmed social URL beyond Telegram, no public mobile-download destination, and no verified hardware model/photo, mounting method, compatibility list or specification. Contact and FAQ make the boundaries clear.
- Manufacturer-reference/editorial-image usage rights still require owner review; no endorsement is asserted. New image provenance is available above.
- Mobile simulated LCP exceeds target. Server logs warn that PostHog has no API key in this local configuration; no production analytics configuration or consent-provider deployment verification is claimed.
- No production deployment is authorised here. The local preview is not a publicly reachable customer URL.

## Parent Final Acceptance

- Independently inspected new Higgsfield assets and desktop/mobile home, process, equipment and journal screenshots.
- Fresh Astra reviewer identified one locale regression: Journal navigation from an English article could follow the cookie/default back to Russian. Reproduced with a failing component test; fixed the shared navigation destination to `/blog/${locale}`. The test now verifies language and active state, and a production browser check covered absent and Russian locale cookies.
- Polished headings that had lost sentence separation when periods were removed. No terminal periods were reintroduced.
- Re-ran lint, typecheck, all 203 tests and production build after final edits. Restarted the owned port 3000 preview with that build.
- Re-ran all 57 core route/viewport browser cases against port 3000 after the last copy change; zero failures, including axe and interaction checks. Exact final browser artifacts: `/tmp/skatelab-public-final-check/report.json` and screenshots in that directory. Earlier English/detail and Lighthouse evidence above identifies the worker build; performance was not remeasured after the final copy/navigation-only edits.
- Final source diff passes `git diff --check`. Completed source, content, assets, plan and report are included in the delivery commit.
