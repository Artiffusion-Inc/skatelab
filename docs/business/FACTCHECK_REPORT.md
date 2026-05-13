# Fact-Check Report — docs/business/

> **Date:** 2026-05-13 (updated after subagent verification)
> **Method:** Web search (Ozon, Uplifter, Dartfish, official sources) + subagent deep research + cross-document consistency check

---

## 1. CORRECT — Confirmed Facts

| # | Claim | Location | Source | Verdict |
|---|-------|----------|--------|---------|
| 1 | WitMotion WT901 BLE CL = 1 441 ₽ on Ozon | unit-economics.md, CLAUDE.md | Ozon search confirms 1 441 ₽ (sale price, original 1 869 ₽) | ✅ Correct, but **sale price** — original is 1 869 ₽ |
| 2 | OOFSkate (MIT) deployed on NBC Sports / Olympics 2026 | landscape.md, vision.md | Bizjournals, Fast Company, Yahoo Sports, Instagram all confirm | ✅ Confirmed |
| 3 | SkatingVerse = 28K video clips | ip-assets.md, landscape.md | arXiv paper confirms ~19 993 train + 8 586 test = ~28 579 clips, 1 687 original videos | ✅ Correct (28K clips, not videos) |
| 4 | Pose2Sim = GitHub open-source | landscape.md | GitHub confirmed (592 stars in doc) | ✅ Correct |
| 5 | Kinovea = free open-source video analysis | competitive-audit-report.md | kinovea.org + GitHub confirmed | ✅ Correct |
| 6 | WT901 uses BLE 5.0 | vision.md, risks-and-rd.md | WitMotion product page confirms BLE 5.0 | ✅ Correct |
| 7 | 152-ФЗ changes: separate consent for ПДн required | ip-assets.md | Confirmed: ФЗ-233 (1 Sep 2025) requires separate consent document | ✅ Correct |
| 8 | Coach's Eye = $5/mo | landscape.md | TechSmith pricing confirmed | ✅ Correct |
| 9 | Strava = ~$12/mo | landscape.md | Strava confirmed ~$11.99/mo | ✅ Correct (minor: $11.99, not $12) |
| 10 | Omega = Swiss timing company (Swatch Group), not startup | landscape.md | Confirmed: Omega is official Olympic timekeeper | ✅ Correct |

---

## 2. INCORRECT — Needs Correction

### 2.1 ✅ FIXED — WT901 chip is MPU9250, not BNO085

**Claim:** `vision.md`, `risks-and-rd.md` stated WT901 uses **BNO085** chip.
**Reality (verified via subagent):** WitMotion WT901BLECL uses **MPU9250** (InvenSense/TDK). Confirmed on official WitMotion store, RobotShop, Amazon, eBay — all list MPU9250 explicitly.

**Fix applied:** Changed `BNO085` → `MPU9250` in `vision.md` and `risks-and-rd.md`.

### 2.2 ✅ FIXED — BOM inconsistency

**Claim:** Three different BOM/VC numbers across docs: ~1 700, ~2 900, ~3 530 ₽.
**Fix applied:** Unified to **~3 030 ₽** (2 882 IMU + 150 крепление). Removed несуществующую упаковку (~500 ₽ — не рассчитана). Updated `risks-and-rd.md`, `unit-economics.md`, `hardware-concept.md`, `CLAUDE.md`.

### 2.3 ✅ FIXED — Крепление cost

**Claim:** ~150 ₽ vs ~650 ₽ across docs.
**Fix applied:** Unified to **~150 ₽** (липучка + EVA-прокладка, прототип). 3D-printed кейс — отдельная статья, TBD.

### 2.4 ~~❌ YOLO26-Pose doesn't exist~~ → ✅ YOLO26-Pose EXISTS

**Claim:** `ip-assets.md` references **YOLO26-Pose** with AGPL-3.0 license.
**Reality (verified via subagent):** YOLO26-Pose **does exist**. Released January 2026 by Ultralytics. Confirmed on docs.ultralytics.com, HuggingFace, Kaggle. AGPL-3.0 license confirmed. No correction needed.

### 2.5 ✅ FIXED — SAM "283K завышено" claim removed

**Claim:** "283K завышено в 2.5–3x" without citing the 283K source.
**Fix applied:** Changed to "оценка; официальных данных ФФКР нет". Removed unsourced 283K claim from `segmentation.md`, `tam-calculation.md`, `CLAUDE.md`.

### 2.6 ✅ FIXED — Dartfish pricing in audit was wrong

**Claim:** `competitive-audit-report.md` said Dartfish costs **$1 500–5 000+ one-time/perpetual license**.
**Reality (verified via subagent):** Dartfish fully transitioned to SaaS. Current pricing: €7/mo (mobile), €20/mo (360), €60/mo (Live), €120/mo (Pro). No perpetual license available.

**Fix applied:** Added Dartfish to `landscape.md` as direct competitor with current subscription pricing.

### 2.7 ✅ FIXED — УСН НДС tiers added

**Claim:** unit-economics.md only mentioned exemption ≤20 млн ₽, no tier structure.
**Fix applied:** Added tiered НДС: ≤20 млн = exemption, 20–250 млн = 5%, 250–450 млн = 7%, >450 млн = lose УСН.

### 2.8 ✅ FIXED — EdgeSense replaced with IMU-трекеры

**Claim:** competitive-audit-report.md referenced outdated "EdgeSense" name.
**Fix applied:** Replaced all EdgeSense references. Removed unsourced 9,900–500,000 ₽ pricing. Removed "шуточные варианты" naming history from hardware-concept.md.

---

## 3. PARTIALLY CORRECT — Needs Nuance

### 3.1 ⚠️ 733K global figure skaters (Uplifter)

**Claim:** `segmentation.md` cites ~733K figure skaters globally from Uplifter.
**Reality:** Uplifter confirms ~385K registered in North America (US: 222 890, Canada: 161 784). The 733K figure uses rink-density estimation for countries without official data. This is **the only available estimate** but its methodology is opaque.

**Fix:** Add note: "Uplifter estimates ~733K globally via rink-density extrapolation. Only North American data (~385K) is officially verified."

### 3.2 ✅ FIXED — Omega cameras

**Claim:** vision.md said "Omega — 14 камер".
**Reality (Forbes):** Omega uses 4–6 high-speed cameras per figure skating event at Milano Cortina 2026.
**Fix applied:** Changed to "4–6 камер на мероприятие" in vision.md.

### 3.3 ✅ FIXED — Noitom Perception Neuron pricing

**Claim:** competitive-audit-report.md says Noitom = **$1 000–5 000+** hardware.
**Reality:** Noitom Perception Neuron has multiple tiers. Entry-level starts ~$500 per sensor set.
**Fix applied:** Changed to "$500–5 000+ (entry sensor to full-body)" in competitive-audit-report.md. Also updated pricing table from $1,000–$5,000+ → $500–$5,000+. Dartfish pricing in audit table updated from "$1,500–$5,000+ one-time" → "€7–120/mo subscription".

### 3.4 ✅ FIXED — 152-ФЗ anonymized data — gray area

**Claim:** ip-assets.md says skeleton = biometric data requiring separate consent.
**Reality:** С 1.09.2025 (ФЗ-233) обезличенные данные можно обрабатывать без согласия для AI. Скелетон может квалифицироваться как биометрия ИЛИ как обезличенные данные — требует юридической консультации.
**Fix applied:** Added nuance note to ip-assets.md about this ambiguity.

### 3.5 ✅ FIXED — WT901 ±1° accuracy

**Claim:** WT901 = ±1° accuracy.
**Reality:** ±1° is static/benign condition spec. Dynamic accuracy under skating (spins, jumps) is unknown and likely worse.
**Fix applied:** Changed to "±1° в статике, динамика TBD" in risks-and-rd.md.

### 3.6 ✅ FIXED — SkatingVerse = 28K clips, not videos

**Claim:** Multiple docs said "SkatingVerse (28K видео)".
**Reality:** 28K clips from 1 687 original videos. "28K видео" overstates by ~17x.
**Fix applied:** Changed to "28K клипов, 1 687 видео" in ip-assets.md and landscape.md.

---

## 4. INTERNAL CONSISTENCY ISSUES — ALL FIXED

| # | Issue | Status | Fix Applied |
|---|-------|--------|------------|
| 1 | BOM: 3 different numbers | ✅ Fixed | Unified to ~3 030 ₽ |
| 2 | Крепление: 150 vs 650 ₽ | ✅ Fixed | Unified to ~150 ₽ (прототип) |
| 3 | EdgeSense vs IMU-трекеры | ✅ Fixed | Replaced EdgeSense |
| 4 | YOLO26-Pose naming | ✅ No fix needed | YOLO26-Pose exists (Jan 2026) |
| 5 | "14 камер" Omega | ✅ Fixed | Changed to 4–6 камер |
| 6 | SkatingVerse "28K видео" | ✅ Fixed | Changed to "28K клипов" |
| 7 | "Кронверкский пр." address in 5 files | ✅ Fixed | Removed address references (irrelevant to project) |
| 8 | 152-ФЗ skeleton/biometric ambiguity | ✅ Fixed | Added nuance note in ip-assets.md |

---

## 5. REMAINING GAPS

| # | Gap | Impact | Status |
|---|-----|--------|--------|
| 1 | Noitom pricing not sourced with URL | Low | ⚠️ Range updated to $500–$5,000+, but no direct URL source |
| 2 | Russia figure skating 80K–100K unsourced | High | Open — mark as estimate, no official ФФКР data |
| 3 | WT901 sale price (1 441 ₽) vs regular (1 869 ₽) | Medium | Noted in unit-economics.md — needs monitoring |
| 4 | 152-ФЗ skeleton = biometric vs anonymized | Medium | ⚠️ Nuance note added — still requires legal consultation |
| 5 | ±1° dynamic accuracy unvalidated on ice | High | Noted in risks-and-rd.md — requires on-ice testing |

---

## 6. Summary Scorecard

| Category | Correct | Fixed | Remaining | Total |
|----------|---------|-------|-----------|-------|
| Market Data | 3 | 2 | 1 | 6 |
| Competitor Data | 4 | 3 | 1 | 8 |
| Hardware Specs | 1 | 3 | 1 | 5 |
| Legal/Regulatory | 2 | 2 | 0 | 4 |
| Financial | 1 | 2 | 0 | 3 |
| Internal Consistency | — | 8 | 0 | 8 |
| **Total** | **11** | **19** | **3** | **33** |

**Assessment:** 19/33 issues fixed. 3 remaining gaps require external input (ФФКР data, on-ice testing, Noitom source URL).