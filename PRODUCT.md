# Product

## Register

product

## Users

**Primary: Coaches and sports schools (B2B).** They pay for efficiency: faster technique analysis, objective data to resolve coach-athlete disputes, scalable progress tracking across multiple students. A coach who saves 10-20 minutes per training session can take more students or reinvest that time into quality.

**Secondary: Professional and competitive figure skaters.** They buy acceleration: every week of stalled progress costs roughly 3,500-14,000 rubles in wasted training time (CustDev: one session ~3,500 rubles, 24 sessions/month). They need objective proof that their technique is right or wrong, not more subjective opinions.

**Tertiary: Parents of child athletes.** They need visible, measurable progress to justify 5,000-20,000 rubles/month in training costs. They want confidence that the coach delivers results.

**Future segments:** Federations/judges (objective scoring standard), rehab centers (technique recovery), blade manufacturers (embedded sensors), media/broadcasts (real-time analytics overlay).

**Context:** Users record training videos on ice (phone or camera), upload to the platform, and receive biomechanical analysis within minutes. Coaches review student analytics remotely. IMU sensors (EdgeSense) on each skate blade provide real-time edge angle, rotation speed, and glide dynamics, synchronized with video like VAR in football.

**Job to be done:**
- For coaches: get fast, objective feedback on student technique without spending 10-20 minutes per session on manual video review. Reduce coach-athlete disputes with data, not opinions.
- For skaters: understand exactly what to fix and see proof of progress. Stop wasting training hours on misdiagnosed errors.
- For schools: differentiate their program with technology. "Our coaches use objective data" is a competitive advantage.

## Product Purpose

AI-powered figure skating coach with IMU sensor integration: video analysis, real-time blade edge detection, progress tracking, and coach-student connection platform.

**Core proposition:** "Measure technique, don't guess." If you train without trackers, you lose to those who use them.

**Key outcomes:**
- Video upload → biomechanical analysis (pose, 12+ metrics, phase detection, recommendations in Russian) delivered in under 15 seconds per frame.
- EdgeSense IMU sensors → real-time edge angle, rotation count, glide speed synchronized with video (VAR for figure skating).
- Persistent progress tracking with dashboards, PRs, and trend charts.
- Coach-student relationship platform with shared session visibility and remote feedback.
- Choreography generation and planning with music analysis and CSP solver.
- Future: H-Sense blade-angle tracking, digital judging standard for federations.

**MVP hypotheses (validated via CustDev, N=3):**
- H1: Coaches use objective data during analysis → confirmed
- H2: Data accelerates training review → confirmed
- H3: Athletes trust digital metrics → partially confirmed (trust is the barrier)
- H4: Product reduces repeated errors → hypothesis
- H5: Users will pay → confirmed conditionally (effectiveness must be proven first)

**Critical validation risk:** If the product doesn't show "accelerated progress" in the first weeks of use, it won't be adopted. Speed of demonstrated value is existential.

## Brand Personality

**Three words:** точный, спортивный, уверенный

**Voice:** Direct, confident, no fluff. Athletic precision meets cold technology. Never clinical, never warm. The interface is a laboratory instrument: every element has a purpose, every metric earns its place. Russian-first; all feedback and recommendations in Russian.

**Emotional goals:**
- For skaters: empowerment and clarity. "I can see exactly what to fix, and I can measure my improvement."
- For coaches: control and credibility. "I have objective data to back my coaching, and I can track every student without being on the ice."
- For schools: competitive edge. "Our program uses the same technology as national teams."

**References:** Strava for UX organization (activity-centric, clear hierarchy), but colder and sharper. Not the orange heatmap, not the social feed. Superhuman for the editorial precision: tight typography, disciplined whitespace, single-action CTAs, three-canvas color rhythm (indigo/white/teal). The interface should feel like reading a well-set research paper, not scrolling a social media app.

## Anti-references

- **Generic SaaS cream** — Linear clones, warm beige palettes, soft rounded everything, "friendly" shadows.
- **Crypto neon** — aggressive gradients, glowing accents, dark-mode-by-default edginess, glassmorphism on product screens.
- **Health-tech softness** — pastel colors, gentle curves, overly reassuring copy, therapeutic aesthetics.
- **Toy-like / game UI** — playful illustrations, cartoonish icons, gamification badges, confetti, progress bars with celebration animations.
- **Raw engineering dashboard** — monospace dumps, terminal aesthetics, unstyled data tables, engineering-first at the expense of usability.
- **Direct Strava clone** — take UX structure inspiration, never the orange heatmap, never the social feed layout.
- **Winter cliché** — snowflake icons, frosted decorative borders, "frozen glass" effects, seasonal pastel gradients. Ice identity is expressed through hue and precision, not literal winter imagery.

## Design Principles

1. **Speed is a feature** — every interaction must feel snappy. Load states are informative, never blocking. Perceived performance matters as much as actual. The product must demonstrate accelerated progress in the first weeks or it fails.
2. **Precision over decoration** — clean lines, disciplined spacing, no ornamental flourishes. Every pixel should serve the athlete's understanding, not the designer's ego.
3. **Data at a glance** — metrics and progress should be scannable in under 2 seconds. No buried insights. Score colors always paired with icons or numeric labels for accessibility.
4. **Ice as identity, not cliché** — the cold aesthetic (indigo navy, teal, violet accents) reflects the sport without falling into generic winter tropes. The Superhuman three-canvas rhythm (indigo hero, white body, teal closing) gives the brand editorial weight.
5. **Objective confidence** — the interface should feel like an instrument you trust, not a toy you play with. Weight 460/540/700 typography. Warm ink (#292827, never pure black) on white canvas. Single CTA per section. Nothing competing for attention.

## Accessibility & Inclusion

- **WCAG 2.1 AA** as baseline.
- **Reduced motion:** Respect `prefers-reduced-motion`. Replace animations with instant state changes. No bounce, no elastic easing.
- **Colorblind-safe metrics:** Score indicators (good/mid/bad) must not rely on color alone. Use weight, iconography, or numeric labels alongside OKLCH hues.
- **Touch targets:** Minimum 44x44px on mobile (WCAG AAA). 48x48px on bottom dock navigation.
- **Russian-first i18n:** All primary copy in Russian. English as secondary. Right-to-left not required.
