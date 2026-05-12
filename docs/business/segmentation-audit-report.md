# Segmentation Audit Report

> Date: 2026-05-07  
> Auditor: Business Analyst  
> Source: `docs/business/02-market/segmentation.md`, `abcd-segmentation.md`, `tam-calculation.md`, `custdev-results.md`

## Executive Summary

The current segmentation is **directionally sound** but contains **material gaps in sizing consistency, missing segments, and prioritization nuance**. ABCDX methodology is applied correctly at the qualitative level. The biggest risk: TAM ($36.1M bottom-up) is calculated for all markets but heavily weighted toward Russian-speaking skaters (SAM ~$3M), implying limited non-Russian validation. This is a strategic constraint (Russian-first) that must be stated explicitly.

---

## 1. MASADA Evaluation per Segment

| Segment | Measurable | Accessible | Substantial | Differentiable | Actionable | Verdict |
|---------|-----------|------------|-------------|----------------|------------|---------|
| A1 — Elite coaches | Size: ~20K coaches. Sourced via academies/federations. | Yes: direct sales, conferences, pilot programs. | $9.6M/yr. High value per account. | Yes: B2B buyer, values dashboard + metrics. | **High**: Offer, price, process, case study path defined. | Strong |
| A2 — Advanced skaters | Size: ~50K. Self-serve signup. | Yes: Instagram/Telegram, skating forums. | $15M/yr at 100% penetration. | Yes: self-serve, GOE proxy metric. | **High**: Self-serve motion clear. | Strong |
| B1 — Choreographers | Size: ~5K. Loose sourcing. | Partial: via coaches, competitions. | $2.4M/yr. | Yes: music-analysis need is unique. | **Medium**: Product exists but no case studies; objections documented. | Good |
| B2 — Parents | Size: ~100K (implied). | Partial: channels not defined (parent forums? clubs?). | $18M/yr. Very high emotional WTP. | Yes: safety + progress tracking motive. | **Medium**: Offer defined, but process lacks distribution plan. | Needs work |
| C1 — Beginners | Size: ~200K. | Freemium / app stores. | Low ARPU ($0–$5/mo). | Yes: motivation vs technique. | **Low**: Correctly deprioritized. | Acceptable |
| C2 — Small clubs | Size: ~3K academies (split unclear). | Inside sales? | $7.2M/yr at 100%. | Yes: group management need. | **Medium**: Plan exists, no case study. | Acceptable |
| D1 — Federations | Size: ~50. | Long cycle, procurement. | $0.3M/yr. | Yes: benchmarking need. | **Low**: No product, no case, 12–24 mo sales cycle. | Correctly parked |
| D2 — Solo hobbyists | Not sized. | App stores. | Zero revenue. | N/A. | **None**. Correctly parked. | Acceptable |
| X1 — ISU Judges | Not sized. | Impossible without ISU cert. | Unknown. | Real-time overlay need. | **None today**: <1s latency + certification required. | Correctly parked |
| X2 — Broadcast | Not sized. | Sports broadcasters. | Unknown. | Overlay metrics. | **None today**: Real-time not built. | Correctly parked |

**Key finding:** All A/B/C/D/X segments have clear objections and value propositions. Weakness is in **Accessibility** (channels undefined for parents) and **Measurability** (some segments lack explicit sizing in ABCDX file, e.g., X1, X2, D2).

---

## 2. ABCDX Actionability Score

Actionability = clarity of offer + reachable channel + product readiness + case study availability.

| Segment | Score | Rationale |
|---------|-------|-----------|
| A1 — Elite coaches | 9/10 | Full go-to-market motion; needs pilot validation only. |
| A2 — Advanced skaters | 9/10 | Self-serve ready; CustDev confirms 500–600 ₽/mo WTP. |
| B1 — Choreographers | 6/10 | Offer defined, product in architecture, but **no case study** and objection is strong ("I already do this manually"). |
| B2 — Parents | 5/10 | Offer defined, but **CustDev missing** (N=0 parents interviewed). Channel unclear. |
| C1 — Beginners | 4/10 | Freemium trap; correctly labeled "do not spend resources." |
| C2 — Small clubs | 5/10 | Budget constrained; needs land-and-expand from coach-tier. |
| D1 — Federations | 2/10 | No product, long cycle. Keep warm via A1 coaches who have federation relationships. |
| D2 — Solo hobbyists | 1/10 | No monetization path. |
| X1 — Judges | 1/10 | Blocked by real-time requirement + ISU certification. |
| X2 — Broadcast | 1/10 | Blocked by real-time overlay. |

**Red flag:** B2 (Parents) outranks C2 (Small clubs) in the current priority list, yet parents have zero CustDev data and undefined channels. Small clubs have a clearer upsell path from existing coach users.

---

## 3. Segment Sizing Validation

### Inconsistencies Found

| Issue | Location | Severity |
|-------|----------|----------|
| **TAM/SAM inversion** | `segmentation.md` vs `tam-calculation.md` | **Critical** |
| **Top-down vs bottom-up gap** | `segmentation.md` lines 17–30 | **High** |
| **Coach count mismatch** | `segmentation.md` says 50K coaches; detailed calc uses 20K | **Medium** |
| **Active user ratio** | 25% of 2M = 500K. Detailed calc sums to 355K skaters. | **Medium** |
| **CustDev N=3, 0 parents** | `custdev-results.md` | **High** for B2 |

#### 3.1 TAM/SAM Inversion

- Bottom-up TAM (global): **$36.1M** at 100% penetration (`tam-calculation.md`).
- SAM (Russian-speaking only): **~$3M** (`segmentation.md`).

**Problem:** SAM is ~8% of TAM, which is plausible for a Russian-first product. However, the bottom-up TAM may still undercount global markets (US, Canada, Japan, Korea, Europe) where figure skating is larger but SkateLab has no localization or distribution.

**Likely root cause:** The bottom-up detailed calculation silently counts only segments SkateLab currently considers, not all global active figure skaters. The summary table’s 500K active skaters is plausible globally, but the revenue math only adds up to 355K + 20K coaches + 3K academies.

**Recommendation:** The $36.1M bottom-up TAM is plausible for a Russian-first product with limited global distribution. If expanding globally, recalculate TAM with full 500K skaters + 50K coaches + 5K clubs across all markets (US, Canada, Japan, Korea, Europe) — likely $200M+.

#### 3.2 ARPU Realism

| Segment | ARPU Claim | CustDev Validation | Status |
|---------|-----------|-------------------|--------|
| A2 Advanced skaters | $15–30/mo | Athlete (16y, MS) willing to pay 500–600 ₽/mo (~$6–7). | **Overstated 2–4x**. Needs price testing. |
| A1 Elite coaches | $30–50/mo | Coaches: "ready to pay if proven effective." No number given. | **Unvalidated**. |
| B2 Parents | $10–20/mo | No interviews. | **Unvalidated**. |

**Critical insight:** The athlete willing to pay the most stated **$6–7/mo**, while the model assumes $15–30/mo for advanced skaters. Either the segment is smaller at this price point, or the price must drop. A2 ARPU should be stress-tested at $5/mo to see if the segment still holds.

---

## 4. Priority Recommendations

Current priority list is mostly correct, but **A2 should rank above A1** for MVP-stage resource allocation, and **B2 should be deprioritized until CustDev is done**.

### Revised Priority (Next 12 Months)

| Priority | Segment | Action | Rationale |
|----------|---------|--------|-----------|
| **P0** | A2 — Advanced skaters | Self-serve launch, $5–10/mo price point. | Lowest CAC, highest willingness per CustDev, immediate feedback loop. |
| **P1** | A1 — Elite coaches | 3 pilot programs (academies). B2B sales after proof. | High value, but requires case study + longer cycle. Use A2 success as social proof. |
| **P2** | C2 — Small clubs | Bundle via coach-tier (A1 upsell). | Natural expansion from coaches already using dashboard. |
| **P3** | B1 — Choreographers | Finish Choreography Planner MVP, then 2 pilot users. | Product-dependent; do not market before feature-complete. |
| **P4** | B2 — Parents | **HOLD**: Run 5 parent interviews first. | Zero data; high risk of building the wrong thing. |
| **P5** | C1 — Beginners | Freemium only, zero paid marketing. | Correctly deprioritized. |
| **P6** | X1 / X2 / D1 | Monitor, do not build. | Real-time requirement blocks both. Federation sales 18+ months out. |

---

## 5. Missing Segments Worth Considering

| Segment | Size Estimate | Opportunity | Fit with Current Product |
|---------|--------------|-------------|------------------------|
| **Adult / Masters skaters** | Growing globally; high disposable income; often self-funded. | High WTP, self-serve friendly, no gatekeeper (coach). | High — same A2 product. |
| **Remote / Online coaches** | Post-pandemic segment; not bound to rinks. | Same B2B motion as A1 but lower touch. | High — dashboard + async video review. |
| **Physical therapists / Sports med** | High injury sport; rehab tracking. | B2B2C: clinics prescribe SkateLab for gait/skating rehab. | Medium — needs new metrics (landing impact, asymmetry). |
| **Ice rink owners / Arena ops** | ~5K rinks globally. | Facility analytics: usage, skater flow, safety. | Low — no product today, but data aggregation possible. |
| **Pair & Ice Dance specialists** | Subset of A2/B1. | Different metrics (synchronization, lift mechanics). | Low — product is singles-focused today. |
| **Blade / Boot manufacturers** | Small but high budget. | Aggregate biomechanical data for R&D. | Low — requires anonymized dataset sales model. |

**Top recommendation:** Add **Adult / Masters skaters** as an A2 sub-segment. They are measurable (age data on signup), accessible (social media), substantial (self-funded, time-rich), and actionable immediately with the existing self-serve product.

---

## 6. Action Items

| # | Action | Owner | Deadline | Success Metric |
|---|--------|-------|----------|----------------|
| 1 | **Fix TAM/SAM inversion**: Recalculate global TAM including non-Russian markets; clearly label $36.1M as SAM if Russian-only. | BizDev / Analyst | 2026-05-14 | One consistent TAM/SAM/SOM table |
| 2 | **Validate A2 ARPU**: Price sensitivity survey with 20+ advanced skaters; test $5 vs $10 vs $20/mo. | Product / Marketing | 2026-05-21 | Price-demand curve; revised ARPU |
| 3 | **CustDev for B2 (Parents)**: 5 interviews with parents of skaters 6–14y. Validate WTP and channel. | CustDev lead | 2026-05-28 | Interview notes; go/no-go for P4 |
| 4 | **Define channels for B2**: If CustDev positive, document acquisition channel (parent Telegram/FB groups, club partnerships). | Marketing | 2026-06-04 | Channel CAC estimate |
| 5 | **Pilot A1 motion**: 3 academy pilots, 30-day free, coach onboarding checklist. | Sales / CS | 2026-06-15 | 3 pilots active; NPS from coaches |
| 6 | **Add Adult/Masters sub-segment**: 2-sentence insert into segmentation.md and abcd-segmentation.md. | BizDev | 2026-05-10 | Docs updated |
| 7 | **Reconcile user counts**: Ensure bottom-up user totals (skaters + coaches + clubs) match the 500K/50K/5K summary or explain variance. | Analyst | 2026-05-14 | Footnotes in tam-calculation.md |
| 8 | **Sensitivity analysis for ARPU**: Re-run SOM table with A2 ARPU = $5/mo (pessimistic) and $15/mo (base). | Analyst | 2026-05-14 | Revised SOM range |

---

## Appendix: Quick Reference — Segment Sizes

| Segment | Users | ARPU/mo | Annual (100%) | Source |
|---------|-------|---------|---------------|--------|
| A1 Coaches | 20,000 | $40 | $9.6M | `tam-calculation.md` |
| A2 Advanced | 50,000 | $25 | $15.0M | `tam-calculation.md` |
| A2 (stress test) | 50,000 | $7 | $4.2M | CustDev-derived |
| B1 Choreographers | 5,000 | $40 | $2.4M | `tam-calculation.md` |
| B2 Parents | 100,000 | $15 | $18.0M | `tam-calculation.md` |
| C1 Beginners | 200,000 | $10 | $24.0M | `tam-calculation.md` |
| C2 Small clubs | 3,000 | $200 | $7.2M | `tam-calculation.md` |
| D1 Federations | 50 | $500 | $0.3M | `tam-calculation.md` |

**Bottom line:** The segmentation framework is solid. Fix the numbers, validate A2 pricing, interview parents before building, and move Adult/Masters into the active targeting list.
