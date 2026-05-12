# Competitive Audit Report

> **Date:** 2026-05-07
> **Scope:** docs/business/03-competitive/landscape.md, 01-product/vision.md, 06-gtm/positioning.md, 04-financial/unit-economics.md

---

## 1. Executive Summary

The current competitive landscape document covers 6 direct and 3 indirect competitors with a basic differentiation matrix. The analysis has material gaps in:

- Missing well-established direct competitors (Kinovea, Dartfish, IMU-based systems)
- Incomplete feature comparison (missing matrix columns and rows)
- No structured pricing comparison against competitors
- Moats described but not stress-tested for sustainability
- White spaces not explicitly identified

**Verdict:** The landscape is a solid MVP but needs expansion before investor or GTM use.

---

## 2. Missing Competitors

### 2.1 Direct — Kinovea (Open Source Video Analysis)

| Parameter | Detail |
|-----------|--------|
| What | Free video analysis software widely used in figure skating coaching |
| Strengths | Angle measurement, dual-video comparison, slow-motion, path tracking, 20K+ community |
| Weaknesses | Manual annotation only, no ML, no 3D, no cloud/SaaS, no Russian localization |
| Pricing | Free |
| Threat level | **Medium-High** — SkateLab's core value prop is "automated Kinovea + Russian + 3D". If Kinovea adds ML or a coach adds manual annotation, the SkateLab free tier loses differentiation. |

### 2.2 Direct — Dartfish (Professional B2B Video Analysis)

| Parameter | Detail |
|-----------|--------|
| What | Olympic-grade video analysis used by national federations across sports |
| Strengths | B2B sales motion, federations trust it, high-precision tools, team dashboards |
| Weaknesses | Expensive ($1,500–$5,000+ per license), not skating-specific, no Russian localization, no ML automation |
| Pricing | $1,500–$5,000+ per seat |
| Threat level | **Medium** — different segment (federations vs. individual coaches), but Dartfish could add an "affordable coach tier" and compete for SkateLab's Coach/Academy segments. |

### 2.3 Direct — Noitom / Perception Neuron (IMU Motion Capture)

| Parameter | Detail |
|-----------|--------|
| What | IMU-based full-body motion capture for sports biomechanics |
| Strengths | 3D kinematics without cameras, real-time data, used in sports science labs |
| Weaknesses | High cost ($1,000–$5,000+), requires wearable sensors, not SaaS, no skating-specific software |
| Pricing | Hardware $1,000–$5,000+; software often bundled |
| Threat level | **Low-Medium** — EdgeSense IMU concept overlaps here. If Noitom creates a skating-specific SDK or partners with a software vendor, SkateLab's hardware+SaaS bundle faces a technically superior but more expensive rival. |

**Why these matter:** All three are active, funded, or have large communities. The current landscape focuses on academic/GitHub projects with minimal traction, while ignoring tools coaches actually use today.

---

## 3. Feature Comparison Matrix Gaps

### 3.1 Missing Columns (Competitors Not in Matrix)

The current matrix includes: SkateLab, Omega, Pose2Sim, Strava, HUDL, Coach's Eye.

**Missing from matrix:**
- JudgeAI-LutzEdge (listed as direct competitor but not in matrix)
- YourSkatingCoach (listed as direct competitor but not in matrix)
- Sports2D (listed as direct competitor but not in matrix)
- Kinovea (widely used, see Section 2.1)
- Dartfish (B2B incumbent, see Section 2.2)

### 3.2 Missing Feature Rows

| Missing Capability | Why It Matters |
|--------------------|----------------|
| Mobile-native app / on-device capture | Coaches film on phones; the workflow starts at the rink, not the desktop. SkateLab's mobile capture controller (`mobile/lib/capture/capture_controller.dart`) exists — this is a real differentiator not listed. |
| Real-time feedback (during jump) | Omega does this with 14 cameras. No consumer product does. White space opportunity. |
| API / integrations (Wearables, LMS, CRM) | Academy tier needs data export. SkateLab has FastAPI backend — API readiness should be highlighted. |
| Offline mode / on-device inference | rink Wi-Fi is unreliable. Competitors (Strava, Kinovea) have offline modes. SkateLab currently requires GPU cloud upload. |
| White-label / B2B custom branding | Academy/Federation tiers need this. Dartfish and HUDL offer it. |
| Bulk upload / batch processing | Coaches have 10–30 videos per session. Current matrix does not compare batch capability. |
| Social sharing / athlete feed | Strava's moat is social. SkateLab explicitly says "social layer is not our value" — correct, but the matrix should flag this as a deliberate trade-off, not an omission. |
| Force/pressure data integration | EdgeSense IMU is conceptual. No competitor in the matrix captures blade pressure or jump force. |
| Historical trend analysis / longitudinal tracking | Critical for coach dashboard value prop. Not explicitly compared in matrix. |

**Recommendation:** Rebuild the matrix with all 9+ competitors and 15+ capability rows. Use a compact format (checkmarks + notes) to keep it readable.

---

## 4. Pricing Positioning vs Market

### 4.1 Current SkateLab Pricing

| Tier | Price | Segment |
|------|-------|---------|
| Free | 0 ₽ | C1 beginners |
| Pro | 990 ₽/mo | A2 athletes |
| Coach | 1,500–3,500 ₽/mo | A1 coaches |
| Choreo | 3,000 ₽/mo | B1 choreographers |
| Club | 5,000–25,000 ₽/mo | C2 clubs |
| EdgeSense (HW) | 9,900–500,000 ₽ | B2C / B2B hardware |

### 4.2 Competitor Pricing Context

| Competitor | Price Point | Model |
|------------|-------------|-------|
| Omega | Unavailable / B2G | Custom federation contracts |
| JudgeAI-LutzEdge | N/A (research) | Hardware + unknown |
| YourSkatingCoach | N/A (paper) | None |
| Pose2Sim | Free (open source) | Self-hosted |
| Sports2D | Free (open source) | Self-hosted |
| Strava | $11.99/mo | Freemium SaaS |
| HUDL | $50+/mo per team | B2B SaaS |
| Coach's Eye | $5/mo | B2C SaaS |
| Kinovea | Free | Open source desktop |
| Dartfish | $1,500–$5,000+ one-time | Perpetual license |
| Noitom | $1,000–$5,000+ hardware | Hardware + software bundle |

### 4.3 Positioning Assessment

**Strengths:**
- SkateLab Pro (990 ₽ ≈ $11/mo) matches Strava's price point — market-validated for consumer sport SaaS.
- Coach tier (1,500–3,500 ₽ ≈ $17–$40/mo) sits between Coach's Eye ($5) and HUDL ($50+). This is the correct "serious but affordable" positioning.
- Hardware bundle (9,900 ₽ ≈ $110) is 5–10x cheaper than Noitom and 10–50x cheaper than Dartfish.

**Gaps:**
- **No annual plan pricing displayed** in landscape.md. Unit economics mention "annual plans with discount" as a churn mitigation tactic, but landscape does not show how annual pricing compares to competitors.
- **No freemium competitor pressure analysis.** Pose2Sim and Sports2D are free and open-source. A technical coach could stitch together Sports2D + Kinovea + a spreadsheet for $0. SkateLab must articulate why 990 ₽/mo is worth it vs. free DIY.
- **EdgeSense pricing is conceptual.** No competitor hardware pricing comparison exists. The positioning doc says "Wearable systems: $600–2000+" — but this is an estimate, not a sourced comparison. A real competitive audit needs sourced hardware pricing (Noitom Perception Neuron starts at ~$1,500; XSens DOT ~$500 per sensor; Dartfish video license ~$2,500).

---

## 5. Moat Analysis: Are Advantages Sustainable?

### 5.1 Moats Listed in Current Landscape

| Moat | Claimed Strength | Sustainability Assessment |
|------|------------------|---------------------------|
| **Data (SkatingVerse 28K, etc.)** | "Крупнейшая коллекция датасетов" | **Weak.** SkatingVerse and AthletePose3D are publicly documented datasets. If competitors can download the same data, this is not a proprietary moat. Sustainable only if SkateLab collects **private, labeled data** from users (with consent) that competitors cannot access. |
| **Russian language** | "Единственный full-stack продукт с native русским" | **Medium-Weak.** Easily replicable. Any competitor with $10K–$50K translation/localization budget can match this. Sustainable only if combined with **cultural nuance** (Russian coaching terminology, ISU rule localization, regional federation integrations) that pure translation cannot copy. |
| **OOFSkate approach** | "Валидирован на Олимпиаде 2026" | **Medium.** If OOFSkate is published research, it is copyable. The validation provides credibility (social proof) but not legal protection. Sustainable only if protected by trade secrets or patents, or if the team has unique expertise to extend it faster than competitors. |
| **Choreography planner** | "ISU elements + CSP solver — уникальный продукт" | **Medium.** Unique today, but a competent competitor could build a similar planner in 3–6 months. Sustainable only if tied to **proprietary music analysis models** or **ISU data licensing** that is hard to replicate. |
| **Anatomical Re-ID** | "Решает real-world проблему... технически сложно повторить" | **Medium-Strong.** This is the most defensible technical moat. Biometric re-ID requires specific domain expertise (sports + computer vision + figure skating body mechanics). However, if published, it can be reimplemented. Sustainability depends on keeping improvements proprietary and staying ahead on accuracy. |

### 5.2 Missing Moats

| Potential Moat | Why It Matters |
|----------------|----------------|
| **Network effects** | None identified. If coaches share athlete data within a school, switching cost rises. Not leveraged. |
| **Switching costs** | No data lock-in strategy discussed. If a coach can export all data and leave, retention is purely product-dependent. |
| **Regulatory / federation partnerships** | ISU or national federation endorsement would create high barriers. Not mentioned. |
| **Brand / community** | CustDev shows Alice's input and tagline testing, but no community flywheel (forum, coach certification, content) is described. Strava's real moat is its social graph; SkateLab has no equivalent. |

**Verdict:** Current moats are **tactical advantages**, not structural barriers. The strongest moat is **Anatomical Re-ID**, but it is a single-engineering-team lead, not a permanent barrier. The business needs to build switching costs (data history, team dashboard workflows, federation integrations) to sustain pricing power.

---

## 6. White Space Opportunities

Opportunities not occupied by any competitor in the current landscape:

| Opportunity | Description | Competitor Gap |
|-------------|-------------|----------------|
| **Mobile-native real-time feedback** | On-device pose estimation giving instant jump metrics at the rink. | Omega is real-time but requires 14 cameras. No consumer mobile product does this. |
| **Injury prevention / rehab analytics** | Landing quality prediction, asymmetry detection for post-injury recovery. | Pose2Sim does biomechanics but not injury prediction. Noitom does motion capture but not rehab-specific software. |
| **B2B white-label for federations** | Branded analytics platform for national skating federations. | Dartfish is generic; HUDL is US-centric. No Russian/skating-specific white-label exists. |
| **Force + video fusion** | Combine IMU/force plate data with video AI for blade-edge validation. | JudgeAI-LutzEdge is a research concept. No product exists. |
| **AI-generated training plans** | Auto-generated daily training recommendations based on metric trends. | None of the listed competitors offer generative training planning. SkateLab's rule-based recommender is a seed for this. |
| **Social / content flywheel** | Auto-generated comparison reels (athlete vs. Olympic reference) for TikTok/Instagram. | Strava has social but not auto-generated video content. High virality potential. |
| **Summer / off-season retention** | Dry-land training analysis (off-ice jumps, floor work) using the same mobile app. | All competitors are ice/rink-specific or generic. SkateLab could own the 12-month athlete lifecycle. |

---

## 7. Action Items

| # | Action | Owner | Priority |
|---|--------|-------|----------|
| 1 | **Add Kinovea, Dartfish, and Noitom to competitive landscape** with full parameter tables and threat ratings. | Product/Marketing | High |
| 2 | **Rebuild feature comparison matrix** to include all 9+ competitors and 15+ capabilities (mobile, offline, API, white-label, batch, social, force integration, trends). | Product | High |
| 3 | **Add sourced hardware pricing** for EdgeSense competitors (Noitom, XSens, force plates) with URLs or datasheets. | Business Analyst | Medium |
| 4 | **Write "Why not free?" positioning** — one-page comparison of SkateLab Pro vs. Sports2D + KinoveA DIY stack. | Marketing | Medium |
| 5 | **Stress-test moats** — document which are public/replicable vs. proprietary. Create plan to convert tactical advantages into switching costs (data export friction, team workflows, federation integrations). | Product/Strategy | High |
| 6 | **Evaluate white space #1 (mobile real-time)** for technical feasibility with on-device ONNX Runtime (mobile GPU/NPU). | Engineering | Medium |
| 7 | **Add annual pricing tier to landscape matrix** and compare to Strava annual / Dartfish maintenance contracts. | Marketing | Low |
| 8 | **Monitor Kinovea roadmap** — if they announce ML features, trigger competitive response planning. | Competitive Intel | Ongoing |

---

*Report written by Business Analyst audit on 2026-05-07. Source files: landscape.md, vision.md, positioning.md, unit-economics.md.*
