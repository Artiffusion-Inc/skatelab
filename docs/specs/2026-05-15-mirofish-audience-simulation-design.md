# MiroFish Audience Simulation for SkateLab

**Date:** 2026-05-15
**Status:** Approved
**Goal:** Validate WTP, pricing, pain points, barriers across 3 audience segments before pilot launch

## Problem

CustDev = 3 interviews. Key gaps:
- **B2B (schools/academies):** 0 interviews. Who decides? Budget? Barriers?
- **A1/A2 (coaches + athletes):** WTP partially validated (10K₽ one-time, 500-600₽/mo), but price points unconfirmed
- **Parents:** Plausible but unvalidated. Motivation unclear ("see progress" vs "protect investment")

## Solution

Use MiroFish (multi-agent simulation) to synthetically validate these gaps. Seed with SkateLab market brief, spawn domain-specific personas, simulate social interactions, extract insights via ReportAgent + post-simulation interviews.

## Stack

| Component | Choice |
|---|---|
| **MiroFish fork** | Upstream (666ghj/MiroFish) |
| **Host** | Docker on home server (or temporary Vast.ai GPU instance) |
| **LLM** | NineRouter (`https://9r.hypcat.net/v1`) — OpenAI-compatible |
| **Embeddings** | Jina AI v3 API (10M tokens free tier) |
| **Agent memory** | Zep Cloud free tier (1,000 credits/month) |
| **Container runtime** | Podman |

## Deployment Architecture

```
Home server / Vast.ai instance
  └── Podman container (mirofish)
       ├── Frontend :3000 (Vue/Vite)
       ├── Backend :5001 (Flask)
       ├── LLM → NineRouter API (OpenAI-compat)
       ├── Embeddings → Jina AI v3 API
       └── Memory → Zep Cloud
```

### Environment Variables

```env
# LLM (NineRouter)
LLM_API_KEY=sk-4d7e8ae80dedc297-1szbqr-de1a5fb8
LLM_BASE_URL=https://9r.hypcat.net/v1
LLM_MODEL_NAME=qwen-plus  # or gpt-4o-mini for budget runs

# Embeddings (Jina AI)
JINA_API_KEY=<get from jina.ai>
JINA_MODEL_NAME=jina-embeddings-v3

# Memory (Zep Cloud)
ZEP_API_KEY=<get from getzep.com>
```

## Simulation Segments

### Segment 1: B2B (Schools/Academies)

**Personas:**
- Club director (бюджет, решение о закупке)
- Academy administrator (операционные барьеры, внедрение)
- Federation official (стандартизация, сертификация)
- Rink owner (инфраструктура, аренда)

**Key questions:**
- Who makes the purchase decision?
- Budget range for coaching tools?
- Barriers: integration with existing workflow, certification requirements, pilot process?
- Is this a top-down (director) or bottom-up (coach request) decision?

### Segment 2: A1/A2 (Coaches + Athletes)

**Personas:**
- National team coach (A1, data-driven, high budget)
- Academy coach (A1, practical, moderate budget)
- Advanced figure skater CSEP+ (A2, self-improvement focus)
- Competitive athlete (A2, results-obsessed, budget-conscious)

**Key questions:**
- WTP validation: 10K₽ one-time? 500-600₽/mo subscription?
- Feature triggers: which feature makes them say "I need this"?
- Price sensitivity curve at different price points
- Objection hierarchy: price vs trust vs workflow disruption

### Segment 3: Parents (B)

**Personas:**
- "Investment parent" (высокие траты на спорт, хочет видеть ROI)
- "Progress parent" (хочет понимать что происходит на тренировках)
- "Anxious parent" (боится травм, хочет объективные данные о технике)
- "Casual parent" (просто возит на каток, минимальная вовлечённость)

**Key questions:**
- Primary motivation: "see progress" vs "protect investment" vs "safety"?
- WTP: separate from coach budget or combined?
- Is this a NEW segment or supporting the coach decision?
- Purchase channel: buy directly or via coach recommendation?

## Seed Document

Dense market brief (~2000-3000 words) covering:

1. **Product:** SkateLab — AI figure skating coach. Video analysis + IMU sensor data → biomechanical feedback in Russian.
2. **Value proposition:** Objective measurement of technique, accelerated progress, reduced coaching subjectivity.
3. **Target segments:** Coaches (A1), athletes (A2), parents (B), clubs (B2B).
4. **Pricing hypothesis:** Hardware 8-12K₽ (BOM ~3K₽), SaaS 500-600₽/mo for coaches, potential B2B licensing.
5. **Competitive landscape:** No direct AI competitors in Russian market. Traditional video review (manual, subjective).
6. **Russian figure skating context:** ~85-115K figure skaters, ФФКР structure, ДЮСШ system, coach certification.
7. **Technology:** MogaNet-B pose estimation, biomechanics metrics, IMU WitMotion WT901 BLE CL.
8. **Current validation:** 3 CustDev interviews (coaches + athlete). Key pains confirmed: subjectivity, slow progress, time cost.

## Simulation Workflow

1. **Deploy** MiroFish Docker container
2. **Configure** `.env` with NineRouter + Jina + Zep credentials
3. **Upload** seed document via MiroFish web UI
4. **Graph building:** MiroFish extracts entities/relations from seed (~7-10 min)
5. **Persona configuration:** Define custom agent templates per segment
6. **Run simulation:** 10-20 rounds, 30-50 agents total
7. **Report generation:** ReportAgent produces structured analysis
8. **Post-simulation interviews:** Chat with key agents for deeper insights
9. **Export + backup:** Save all simulation data
10. **Teardown:** Stop container, archive results

### Custom Persona Template

```python
skatelab_template = TextPrompt(
    """You are {name}, a {role} in the Russian figure skating ecosystem.
    Your experience level: {experience}.
    Your primary concern: {concern}.
    Your budget authority: {budget_level}.
    Your tech savviness: {tech_savviness}.

    You are evaluating SkateLab — an AI figure skating coaching tool
    that analyzes video and IMU sensor data to provide biomechanical
    feedback in Russian.

    Based on the product description, peer discussion, and your
    personal situation, decide: would you purchase, recommend, or pass?
    What are your main objections and triggers?"""
)
```

### Simulation Parameters

| Parameter | Value | Reason |
|---|---|---|
| Agent count | 30-50 | Enough diversity, manageable LLM cost |
| Max rounds | 10-20 | Start low, scale if needed |
| Platform | Reddit-like | Longer-form discussion better for product evaluation |
| Actions | LIKE, COMMENT, CREATE_POST, PURCHASE_PRODUCT | Include purchase decision |
| Temperature | 0.7 | Balance creativity and consistency |

## Expected Outputs

Per segment:
- **Sentiment distribution** (positive/neutral/negative %)
- **Top 5 objections** ranked by frequency
- **Price sensitivity curve** (acceptance at different price points)
- **Feature trigger ranking** (which feature drives adoption)
- **Decision maker map** (who influences whom)
- **Key influencer agents** (which personas drive opinion shifts)

Cross-segment:
- **Segment comparison** (which segment is most receptive)
- **Objection overlap** (common vs segment-specific objections)
- **Pricing sweet spot** across all segments

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Zep Cloud free tier exhausted (1,000 credits) | Can't complete simulation | Start with small runs; upgrade to Flex ($125/mo) if needed |
| LLM token cost high | Budget overrun | Limit rounds <20, agents <50; monitor NineRouter usage |
| Simulation quality depends on model | Shallow insights | Use capable models; validate with real CustDev |
| Jina free tier (10M tokens) insufficient | Embedding failures | Monitor usage; switch to local bge-small on GPU if needed |
| Seed document too vague | Poor persona generation | Write dense, specific market brief with actors, pressure, question |

## Cost Estimate

| Item | Cost |
|---|---|
| MiroFish (open source) | 0 |
| NineRouter LLM API | Usage-based (existing account) |
| Jina AI v3 | Free tier (10M tokens/month) |
| Zep Cloud | Free tier (1,000 credits/month) |
| Vast.ai GPU instance (if needed) | ~$0.10-0.30/hr |
| **Total initial** | ~$0-5 |

## Next Steps

1. Set up Zep Cloud account → get API key
2. Set up Jina AI account → get API key
3. Write seed document (dense SkateLab market brief)
4. Deploy MiroFish Docker container
5. Run first simulation (Segment 2: A1/A2 — most validated baseline)
6. Iterate on remaining segments
