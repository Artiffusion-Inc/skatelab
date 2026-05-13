# JTBD Audit Report — SkateLab Business Knowledge Base

> **Date:** 2026-05-07  
> **Audited files:**
> - `docs/business/02-market/custdev-results.md`
> - `docs/business/06-gtm/positioning.md`
> - `docs/business/02-market/segmentation.md`
> - `docs/business/02-market/abcd-segmentation.md`

---

## 1. Summary Score per Segment

| Segment | Score | Components Present | Critical Gap |
|---------|-------|-------------------|--------------|
| **Coaches** (A1) | **Partial** | 4/5 | Missing proper JTBD statement format |
| **Athletes** (A2) | **Partial** | 4/5 | Missing proper JTBD statement format |
| **Choreographers** (B1) | **Partial** | 4/5 | Missing proper JTBD statement format |
| **Parents** (B2) | **Partial** | 3/5 | Missing JTBD statement + current solution |
| **Clubs** (C2) | **Partial** | 2.5/5 | Missing JTBD statement, current solution, weak pain quantification |
| **Federations** (D1) | **Missing** | 2/5 | Missing JTBD statement, success criteria, weak pain quantification |

**Data quality warning:** CustDev sample is N=3 (2 coaches + 1 athlete). All other segments are inferred from secondary sources; no primary interviews exist for parents, clubs, choreographers, or federations.

---

## 2. Specific Gaps Found

### Coaches (A1)
- **Gap:** No canonical JTBD statement in "When [situation], I want to [motivation], so I can [outcome]" format.
- **Evidence:** `positioning.md` lists "Быстро улучшать технику учеников" (motivation only). `abcd-segmentation.md` A1 describes circumstance, pain, and success criteria but never synthesizes them into a single JTBD sentence.
- **Impact:** Medium. Segment is #1 priority; marketing copy and product requirements risk drifting because the core job is not pinned to a single sentence.

### Athletes (A2)
- **Gap:** No canonical JTBD statement in full format.
- **Evidence:** `positioning.md` lists "Улучшить технику и выигрывать" (motivation only). `abcd-segmentation.md` A2 has rich circumstance and pain data but no synthesized JTBD.
- **Impact:** Medium. Segment is #2 priority and has the highest WTP per user.

### Choreographers (B1)
- **Gap:** No canonical JTBD statement in full format.
- **Evidence:** `positioning.md` places choreographers in "Underserved Segments" with no JTBD table entry. `abcd-segmentation.md` B1 documents circumstance, pain, solution, and success criteria but no "When I..., I want to..., so I can..." sentence.
- **Impact:** Low-Medium. Choreography Planner is a distinct module; missing JTBD may lead to feature scope creep.

### Parents (B2)
- **Gap 1:** No canonical JTBD statement.
- **Gap 2:** Current solution is not documented.
- **Evidence:** `abcd-segmentation.md` B2 documents circumstance ("После тренировки ребёнка"), pain ("35K+ ₽/мес без понимания отдачи"), and success criteria ("Понимание прогресса в цифрах"). However, there is no description of what parents currently do to track progress (e.g., asking the coach, watching videos, using WhatsApp groups).
- **Impact:** Medium. Parents are a trust proxy; unclear current solution means onboarding UX cannot be designed to replace an existing habit.

### Clubs / Academies (C2) — ⚠️ Segment on hold (CustDev = 0)
- **Gap 1:** No canonical JTBD statement.
- **Gap 2:** Current solution is not documented.
- **Gap 3:** Pain is weakly quantified.
- **Gap 4:** Success criteria lack concrete metrics.
- **Gap 5:** Core pain claim ("Отток учеников в академии с лучшей аналитикой") is fabricated — no evidence parents choose clubs by analytics. Club choice driven by coach reputation, location, and price.
- **Evidence:** `abcd-segmentation.md` C2 now marked as unvalidated. CustDev with clubs = 0. All data is hypothetical.
- **Impact:** Downgraded from High to Low. Segment is on hold pending 3–5 interviews with club directors. B2B scaling hypothesis is untested; do not invest product resources until validated.

### Federations (D1)
- **Gap 1:** No canonical JTBD statement.
- **Gap 2:** Success criteria are completely absent.
- **Gap 3:** Pain quantification is vague ("Высокий, но не осознают").
- **Evidence:** `abcd-segmentation.md` D1 documents circumstance ("Стратегические решения, судейство") and current solution ("Бюджет идёт на Omega"). No outcome metrics, no federation-specific JTBD. `positioning.md"` "Underserved Segments" table mentions "Спортивные аналитики" — a different segment.
- **Impact:** Low (for now). Segment is explicitly tagged "рано" (too early). However, without a JTBD, any future partnership conversations will lack a shared definition of success.

---

## 3. Recommended JTBD Statements

### Coaches (A1) — PRIORITY 1
> **When** I am reviewing my athletes' jump technique after practice or before a competition, **I want to** replace subjective visual assessment with objective biomechanical metrics and progress tracking, **so I can** resolve disagreements with athletes instantly, cut analysis time from 10-20 minutes to under a minute, and demonstrate measurable progress to parents and federation scouts.

### Athletes (A2) — PRIORITY 2
> **When** I finish practicing an element and am unsure whether my technique was correct, **I want to** upload a phone video and receive precise biomechanical metrics plus a comparison to a reference jump, **so I can** fix errors in the next attempt instead of repeating them for weeks, and avoid wasting 15-35K ₽/month on ineffective training hours.

### Choreographers (B1) — PRIORITY 3
> **When** I am designing a new competition program and matching elements to music segments before the season starts, **I want to** automatically generate an optimal element layout with automatic TES/TSS/PCS scoring and an SVG rink visualization, **so I can** save 5-10 hours of manual planning per program and ensure the routine fits within time limits and rule constraints.

### Parents (B2) — PRIORITY 4
> **When** my child comes home from training and I want to understand whether the 35K+ ₽/month we spend is producing real progress, **I want to** see objective metrics, visual comparisons, and a simple progress dashboard that I can share with the coach, **so I can** justify the investment, have productive conversations with the coach based on data rather than feelings, and keep my child motivated by showing them tangible improvement.

### Clubs / Academies (C2) — PRIORITY 5
> **When** I am preparing end-of-season progress reports for parents or marketing materials to attract new students, **I want to** demonstrate measurable technical improvement across all my athletes with aggregated dashboards and benchmark comparisons, **so I can** differentiate my academy from competitors, reduce student churn, and justify higher tuition with transparent data.

### Federations (D1) — PRIORITY 6
> **When** I am allocating budget across national training centers or evaluating whether our athletes are closing the gap with top international competitors, **I want to** access aggregated, anonymized biomechanical benchmarking data across the entire national athlete pool, **so I can** make evidence-based resource allocation decisions and reduce reliance on expensive, closed-source systems like Omega.

---

## 4. Action Items — Prioritized by Impact

| Priority | Action | Segment | Effort | Impact | Owner (suggested) |
|----------|--------|---------|--------|--------|-----------------|
| **P0** | Validate the recommended Coach and Athlete JTBD statements with the existing 3 CustDev respondents (async follow-up). | Coaches, Athletes | 2h | High | Product / Alice |
| **P0** | Conduct 3-5 CustDev interviews with **parents** to document current solutions (What do they do today? WhatsApp? Coach chats? Nothing?) and validate the B2 JTBD. | Parents | 1 week | High | Product / Alice |
| **P1** | Conduct 3-5 CustDev interviews with **club directors / academy owners** to test if C2 pain exists at all. Do not assume "analytics drives retention" — ask open questions about real problems and current tools. | Clubs | 1 week | Medium (downgraded — segment on hold) | Product / Alice |
| **P1** | Add canonical JTBD statements to `positioning.md` and `abcd-segmentation.md` for all 6 segments. Update `segmentation.md` to reference them. | All | 4h | Medium | Business Analyst |
| **P2** | Conduct 1-2 exploratory interviews with **choreographers** to validate the B1 JTBD and refine the "5-10 hours saved" claim. | Choreographers | 3 days | Medium | Product |
| **P2** | Define measurable success criteria for Clubs: e.g., "Reduce student churn by 10%", "Cut report prep time from 4h to 30 min". | Clubs | 2h | Medium | Business Analyst |
| **P3** | Schedule 1 informal conversation with a **federation representative** to test the D1 JTBD hypothesis and document their actual strategic planning workflow. | Federations | 2 days | Low | BizDev |
| **P3** | Add a "Current Solution" column to the ABCD segmentation table for all segments where it is missing (Parents, Clubs). | Parents, Clubs | 1h | Low | Business Analyst |

---

## Appendix: Audit Methodology

For each segment, the following 5 criteria were checked against all 4 source files:

1. **JTBD Statement** — Exists in "When [situation], I want to [motivation], so I can [outcome]" format.
2. **Circumstance** — Specific when/where/context is documented.
3. **Pain Quantified** — Obstacle or cost is expressed in numbers (time, money, churn, etc.).
4. **Current Solution** — What the user does today instead of using SkateLab is explicitly described.
5. **Success Criteria** — Measurable outcome or definition of "job done" is documented.

A segment scored **Complete** only if all 5 criteria were satisfied. **Partial** if 3-4 were satisfied. **Missing** if fewer than 3 were satisfied.
