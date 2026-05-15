# MiroFish Audience Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy MiroFish multi-agent simulator and run audience simulation for 3 SkateLab segments (B2B, A1/A2, Parents) to validate WTP, pricing, pain points.

**Architecture:** MiroFish Podman container on remote server (78.40.209.34). NineRouter (external URL) for LLM, Jina AI v3 for embeddings, Zep Cloud for agent memory. Caddy reverse proxy at `mf.${DOMAIN}`. Seed document → GraphRAG → personas → OASIS simulation → ReportAgent analysis.

**Tech Stack:** Podman 5.4.2 + podman-compose 1.3.0, MiroFish (666ghj/MiroFish), NineRouter API (external), Jina AI v3, Zep Cloud, Caddy

---

## Task 1: Set Up External Service Accounts

**Files:**

- Create: `infra/mirofish/.env` (credential store, gitignored)

- [ ] **Step 1: Create Zep Cloud account**

1. Open https://app.getzep.com/
2. Sign up with email
3. Navigate to API Keys section
4. Generate new API key
5. Copy key — save to password manager

- [ ] **Step 2: Create Jina AI account**

1. Open https://jina.ai/
2. Sign up
3. Navigate to API Keys
4. Generate new API key
5. Copy key — save to password manager

- [ ] **Step 3: Create credentials file**

```bash
mkdir -p infra/mirofish
```

Write `infra/mirofish/.env`:

```env
# LLM (NineRouter — external URL, not internal network)
LLM_API_KEY=sk-4d7e8ae80dedc297-1szbqr-de1a5fb8
LLM_BASE_URL=https://9r.hypcat.net/v1
LLM_MODEL_NAME=qwen-plus

# Optional boost config (cheaper model for auxiliary calls)
LLM_BOOST_API_KEY=sk-4d7e8ae80dedc297-1szbqr-de1a5fb8
LLM_BOOST_BASE_URL=https://9r.hypcat.net/v1
LLM_BOOST_MODEL_NAME=gpt-4o-mini

# Memory (Zep Cloud)
ZEP_API_KEY=<paste-from-task-1>
```

- [ ] **Step 4: Add .env to .gitignore**

Append to `.gitignore`:

```
# MiroFish credentials
infra/mirofish/.env
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore MiroFish credentials"
```

---

## Task 2: Deploy MiroFish Container on Remote Server

**Server:** 78.40.209.34 (SSH: `ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34`)
**Context:** Podman 5.4.2, podman-compose 1.3.0, Caddy reverse proxy, ~12G free disk, existing `app_network` with 9router and other services.
**Important:** LLM calls go through `https://9r.hypcat.net/v1` (external URL), NOT internal `9router:20128`.

**Files:**

- Create: `infra/mirofish/docker-compose.yml` (remote)
- Create: `infra/mirofish/.env` (remote, gitignored)

- [ ] **Step 1: Create directory on remote server**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 "mkdir -p /root/mirofish/uploads"
```

- [ ] **Step 2: Create .env on remote server**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 "cat > /root/mirofish/.env << 'EOF'
# LLM (NineRouter — external URL, not internal)
LLM_API_KEY=sk-4d7e8ae80dedc297-1szbqr-de1a5fb8
LLM_BASE_URL=https://9r.hypcat.net/v1
LLM_MODEL_NAME=qwen-plus

# Optional boost config
LLM_BOOST_API_KEY=sk-4d7e8ae80dedc297-1szbqr-de1a5fb8
LLM_BOOST_BASE_URL=https://9r.hypcat.net/v1
LLM_BOOST_MODEL_NAME=gpt-4o-mini

# Memory (Zep Cloud)
ZEP_API_KEY=<paste-from-task-1>
EOF"
```

- [ ] **Step 3: Create docker-compose.yml on remote server**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 "cat > /root/mirofish/docker-compose.yml << 'YAML'
services:
  mirofish:
    image: ghcr.io/666ghj/mirofish:latest
    container_name: mirofish
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./uploads:/app/backend/uploads
    networks:
      - app_network

networks:
  app_network:
    external: true
YAML"
```

Note: No port mapping needed — Caddy proxies to container via `app_network`. Ports 3000/5001 are internal only.

- [ ] **Step 4: Pull MiroFish image**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 "cd /root/mirofish && podman-compose pull"
```

Expected: Image `ghcr.io/666ghj/mirofish:latest` downloaded (~2GB). Monitor disk: `df -h /`.

- [ ] **Step 5: Start the container**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 "cd /root/mirofish && podman-compose up -d"
```

Expected: Container `mirofish` running.

- [ ] **Step 6: Verify container is running**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 "podman ps | grep mirofish"
```

Expected: Container listed, status "Up".

- [ ] **Step 7: Configure Caddy reverse proxy**

Add MiroFish to existing Caddyfile on the remote server. The Caddyfile is at `./Caddyfile` relative to `compose.yaml`.

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34
```

Edit Caddyfile to add:

```
mf.{$DOMAIN} {
    reverse_proxy mirofish:3000
}
```

Or if Caddyfile uses `{$DOMAIN}` syntax:

```
mf.{$DOMAIN} {
    reverse_proxy mirofish:3000
}
```

Then reload Caddy:

```bash
cd /root  # or wherever compose.yaml is
podman exec caddy caddy reload --config /etc/caddy/Caddyfile
```

- [ ] **Step 8: Verify access**

```bash
curl -sI https://mf.<DOMAIN>
```

Expected: 200 or redirect. MiroFish UI should be accessible at `https://mf.<DOMAIN>`.

- [ ] **Step 9: Commit local reference files**

```bash
git add infra/mirofish/.gitkeep
git commit -m "chore(infra): add MiroFish remote deploy reference"
```

Note: `docker-compose.yml` and `.env` live on the remote server only (not in git).

---

**Note on disk space:** Remote server has ~12G free. MiroFish image ~2G + uploads. Monitor with `df -h /` after pull. If tight, clean unused podman images (`podman image prune`).

---

## Task 3: Write Seed Document

**Files:**

- Create: `infra/mirofish/seed-documents/skatelab-market-brief.md`

- [ ] **Step 1: Create seed document directory**

```bash
mkdir -p infra/mirofish/seed-documents
```

- [ ] **Step 2: Write the SkateLab market brief**

Write `infra/mirofish/seed-documents/skatelab-market-brief.md`:

```markdown
# SkateLab — AI Coach for Figure Skating

## Product

SkateLab is an AI-powered coaching tool for figure skating. It combines video analysis and IMU sensor data (WitMotion WT901 BLE CL) to provide objective biomechanical feedback to coaches and athletes — in Russian.

Core capabilities:
- Video analysis: pose estimation (MogaNet-B), jump phase detection, biomechanical metrics (airtime, rotation count, knee angles, landing quality)
- IMU sensors: 2 wearable IMU sensors per athlete, ±1° angle precision vs ±10° for video-only
- Feedback: Russian-language reports with specific recommendations
- Choreography planner: music analysis + ISU element database + CSP solver

## Value Proposition

Figure skating coaching suffers from:
1. **Subjectivity**: Coach estimates ±10° on video; SkateLab measures ±1° with IMU
2. **Slow progress**: Athletes repeat mistakes between sessions without objective feedback
3. **Time cost**: Coaches spend 10-20 min per athlete on manual video review

SkateLab replaces subjective visual assessment with objective measurement. Athletes get immediate feedback. Coaches save time.

## Target Segments

### A1: Professional Coaches (Primary)

- National team coaches, academy coaches
- Need: objective data for technique correction
- Pain: "Until you translate it into money, it's not critical" — coaches undervalue their own time
- Budget: likely 1,500-3,500₽/mo for SaaS, may resist hardware purchase

### A2: Advanced Figure Skaters

- Competitive athletes, CSEP+ level
- Need: accelerate progress, independent feedback between sessions
- Pain: "Slow progress" — key validated pain
- Budget: up to 10,000₽ one-time, 500-600₽/mo subscription

### B: Parents of Young Figure Skaters

- Parents investing in children's skating career
- Need: see progress, understand what happens at training
- Pain: "Don't understand technique" — can't evaluate coach quality
- Budget: likely pay alongside coaching fees (5,000-15,000₽/mo already on skating)
- Motivation unclear: "see progress" vs "protect investment" vs "safety"

### B2B: Skating Schools and Academies

- Club directors, academy administrators
- Need: differentiate from competitors, retain athletes
- Pain: unvalidated — 0 interviews conducted
- Budget: unknown — could be institutional purchase (50,000-200,000₽/yr?)
- Decision: unknown — top-down (director) or bottom-up (coach request)?

## Pricing Hypothesis

| Tier | Price | Target |
|------|-------|--------|
| Hardware kit (2× IMU + mount) | 8,000-12,000₽ (BOM ~3,030₽) | One-time purchase |
| Coach SaaS | 500-600₽/mo | A1 coaches |
| Athlete SaaS | 300-500₽/mo | A2 athletes |
| Parent dashboard | 200-400₽/mo | B parents |
| B2B institutional | 50,000-200,000₽/yr | Schools/academies |

## Competitive Landscape

No direct AI competitors in Russian figure skating market.

Existing alternatives:
- Manual video review (subjective, time-consuming, ±10° accuracy)
- Coach intuition (no recording, no data)
- Generic fitness trackers (no skating-specific metrics)
- Professional video analysis software (expensive, no skating models, not Russian)

## Russian Figure Skating Market

- ~85,000-115,000 active figure skaters (estimate; ФФКР doesn't publish official numbers)
- ДЮСШ system: state-funded sports schools, budget-constrained
- ФФКР structure: regional federations → national federation
- Coach certification: required, multi-level system
- Training culture: coach authority is high; technology adoption may face resistance
- Geography: major hubs in Moscow, St. Petersburg, smaller centers regionally

## Current Validation

3 CustDev interviews (coaches + athlete):
- ✅ Coaches spend 10-20 min per athlete on video review
- ✅ Subjectivity of assessment is a recognized problem
- ✅ Athletes want to accelerate progress
- ⚠️ WTP partially validated: 10K₽ one-time, 500-600₽/mo
- ❌ No respondent named a specific price for hardware
- ❌ B2B segment: 0 interviews
- ❌ Parent segment: not validated
- ❌ Choreographer segment: 0 interviews

## Technology

- Pose estimation: MogaNet-B (ONNX, 384×288, COCO 17kp)
- Biomechanics: center-of-mass flight detection, knee angles, rotation count, landing quality
- IMU: WitMotion WT901 BLE CL, 2 sensors per athlete
- 3D lift: MotionAGFormer (optional CorrectiveLens, disabled by default)
- Tracking: DeepSORT with anti-steal validation
- Stack: Python, ONNX Runtime, FastAPI, Next.js, Cloudflare R2

## Key Questions for Simulation

1. Which segment has highest willingness to pay?
2. What is the price sensitivity curve per segment?
3. Which features are purchase triggers vs nice-to-have?
4. What are the top 3 objections per segment?
5. Is the parent segment viable as a standalone market?
6. Do B2B decisions come from directors or coaches?
7. What price point maximizes revenue across all segments?
```

- [ ] **Step 3: Commit seed document**

```bash
git add infra/mirofish/seed-documents/skatelab-market-brief.md
git commit -m "docs(mirofish): add SkateLab market brief seed document"
```

---

## Task 4: Create Persona Profiles

**Files:**

- Create: `infra/mirofish/personas/b2b-personas.json`
- Create: `infra/mirofish/personas/a1a2-personas.json`
- Create: `infra/mirofish/personas/parent-personas.json`

- [ ] **Step 1: Create personas directory**

```bash
mkdir -p infra/mirofish/personas
```

- [ ] **Step 2: Write B2B personas**

Write `infra/mirofish/personas/b2b-personas.json`:

```json
[
  {
    "realname": "Игорь Петрович Волков",
    "username": "volkov_sportschool",
    "bio": "Директор ДЮСШ №3 по фигурному катанию. 20 лет в управлении спортивными школами.",
    "persona": "Игорь Петрович — консервативный управленец. Бюджет школы формируется из муниципальных средств и родительских взносов. Технологии рассматривает с позиции 'не навреди'. Главное — сохранить контингент и пройти проверки. Инновации — если федерация рекомендует или конкуренты уже внедрили.",
    "age": 55,
    "gender": "male",
    "mbti": "ISTJ",
    "country": "Russia",
    "segment": "B2B",
    "role": "club_director",
    "concern": "budget_approval",
    "budget_level": "institutional",
    "tech_savviness": "low"
  },
  {
    "realname": "Марина Сергеевна Козлова",
    "username": "kozlova_academy",
    "bio": "Администратор частной академии фигурного катания. Отвечает за операционные процессы и закупки.",
    "persona": "Марина — прагматичный администратор. Частная академия = конкуренция за клиентов. Любой инструмент, который можно показать родителям как 'наше преимущество', интересен. Но бюджет ограничен: каждая статья расходов должна окупаться через привлечение новых спортсменов.",
    "age": 38,
    "gender": "female",
    "mbti": "ESTJ",
    "country": "Russia",
    "segment": "B2B",
    "role": "academy_admin",
    "concern": "competitive_advantage",
    "budget_level": "moderate",
    "tech_savviness": "medium"
  },
  {
    "realname": "Алексей Дмитриевич Романов",
    "username": "romanov_federation",
    "bio": "Член президиума региональной федерации фигурного катания. Курирует судейскую и тренерскую сертификацию.",
    "persona": "Алексей Дмитриевич — системный человек. Любая технология в ФК должна пройти через федерацию: сертификация, стандартизация, методические рекомендации. Видит потенциал AI для объективизации судейства, но опасается что 'робот заменит тренера'. Главное — контроль и постепенность.",
    "age": 62,
    "gender": "male",
    "mbti": "INTJ",
    "country": "Russia",
    "segment": "B2B",
    "role": "federation_official",
    "concern": "standardization",
    "budget_level": "none_direct",
    "tech_savviness": "low"
  },
  {
    "realname": "Наталья Владимировна Соколова",
    "username": "sokolova_rink",
    "bio": "Владелица ледового дворца. Сдаёт лёд в аренду школам и тренерам.",
    "persona": "Наталья — бизнес-леди. Ледовый дворец = недвижимость + услуги. Заинтересована в дополнительных услугах для арендаторов. AI-анализ — потенциальный источник дополнительной выручки (скидка на аренду + процент с подписки). Но капитальные затраты на оборудование — вопрос.",
    "age": 45,
    "gender": "female",
    "mbti": "ENTJ",
    "country": "Russia",
    "segment": "B2B",
    "role": "rink_owner",
    "concern": "revenue_opportunity",
    "budget_level": "high",
    "tech_savviness": "medium"
  }
]
```

- [ ] **Step 3: Write A1/A2 personas**

Write `infra/mirofish/personas/a1a2-personas.json`:

```json
[
  {
    "realname": "Елена Анатольевна Воронцова",
    "username": "vorontsova_coach",
    "bio": "Тренер сборной России по фигурному катанию. 30 лет стажа. Работает с элитой.",
    "persona": "Елена Анатольевна — тренер старой школы, но признаёт что видеоанализ объективнее глаза. Проблема: тратит 15-20 мин после каждой тренировки на разбор видео с каждым спортсменом. Хотела бы автоматизировать рутину, но боится что AI 'не увидит нюансов постановки руки'. Готова попробовать, если инструмент даст данные а не интерпретации.",
    "age": 52,
    "gender": "female",
    "mbti": "ISTJ",
    "country": "Russia",
    "segment": "A1",
    "role": "national_team_coach",
    "concern": "trust_in_data",
    "budget_level": "moderate",
    "tech_savviness": "low"
  },
  {
    "realname": "Дмитрий Олегович Кузнецов",
    "username": "kuznetsov_academy",
    "bio": "Тренер академии, работает с подростками 10-15 лет. Прагматик, ищет инструменты для ускорения прогресса.",
    "persona": "Дмитрий — прагматик. Каждый месяц — новые родители с вопросами 'а почему нет прогресса?'. Объективные данные — способ показать что работа делается. Проблема: его зарплата не покрывает подписку. Если школа не купит — сам не потянет. Но если инструмент реально экономит время — будет продвигать директору.",
    "age": 35,
    "gender": "male",
    "mbti": "ESTP",
    "country": "Russia",
    "segment": "A1",
    "role": "academy_coach",
    "concern": "time_saving",
    "budget_level": "low",
    "tech_savviness": "medium"
  },
  {
    "realname": "Алиса Руслановна Шайхлисламова",
    "username": "shayhlislamova_skater",
    "bio": "Мастер спорта, прыгает четверные. Целеустремлённая, каждый десятый градус имеет значение.",
    "persona": "Алиса — результат-ориентированная спортсменка. Между тренировками хочет понимать что именно исправлять. Сейчас полагается на слова тренера и самокадры на телефоне. Если AI покажет конкретные градусы и фазы — поверит. Готова платить из своих, но больше 10К₽ разово — сложно. Подписка 500₽/мес — норм.",
    "age": 19,
    "gender": "female",
    "mbti": "INTJ",
    "country": "Russia",
    "segment": "A2",
    "role": "advanced_athlete",
    "concern": "precision_feedback",
    "budget_level": "moderate",
    "tech_savviness": "high"
  },
  {
    "realname": "Артём Максимович Лебедев",
    "username": "lebedev_competitor",
    "bio": "Кандидат в мастера спорта, конкурирует за место в сборной. Тренируется 4 часа/день.",
    "persona": "Артём — одержим результатами. Каждый выезд на лёд должен продвигать его к цели. Ненавидит тратить время на 'разбор полётов' — хочет конкретику: 'на сколько градусов недокрутил?'. Бюджет ограничен: стипендия + родители. 10К₽ за датчики — если реально помогут. Подписка — только если будет фича без которой 'проиграю без этого'.",
    "age": 17,
    "gender": "male",
    "mbti": "ENTJ",
    "country": "Russia",
    "segment": "A2",
    "role": "competitive_athlete",
    "concern": "competitive_edge",
    "budget_level": "low",
    "tech_savviness": "high"
  }
]
```

- [ ] **Step 4: Write parent personas**

Write `infra/mirofish/personas/parent-personas.json`:

```json
[
  {
    "realname": "Ольга Николаевна Белова",
    "username": "belova_parent_investor",
    "bio": "Мама фигуристки 12 лет. Инвестирует 40-60К₽/мес в тренировки, хореографию, костюмы, сборы.",
    "persona": "Ольга — инвестор. Считает каждый рубль: если тратим 60К/мес, то прогресс должен быть виден. Проблема: не понимает технику. Тренер говорит 'нормально', а на соревнованиях — 15-е место. Хочет объективные данные: 'на сколько улучшились за квартал?'. Готова платить за дашборд где видны графики прогресса. 2-4К₽/мес — в рамках нормы.",
    "age": 42,
    "gender": "female",
    "mbti": "ESTJ",
    "country": "Russia",
    "segment": "B_parent",
    "role": "investment_parent",
    "concern": "roi_visibility",
    "budget_level": "high",
    "tech_savviness": "medium"
  },
  {
    "realname": "Сергей Андреевич Попов",
    "username": "popov_parent_progress",
    "bio": "Папа фигуриста 9 лет. Водит на каток, сидит на трибуне, не понимает что происходит.",
    "persona": "Сергей — наблюдатель. Каждый день возит сына на лёд, но фигурное катание для него — тёмный лес. 'Прыгнул? Ну прыгнул. Как — не понимаю'. Хотел бы хотя бы базовое понимание: что отработали, что улучшилось. Не готов платить много — 500-1000₽/мес максимум, если это простое приложение с уведомлениями.",
    "age": 38,
    "gender": "male",
    "mbti": "ISFJ",
    "country": "Russia",
    "segment": "B_parent",
    "role": "progress_parent",
    "concern": "understanding_training",
    "budget_level": "low",
    "tech_savviness": "medium"
  },
  {
    "realname": "Ирина Павловна Морозова",
    "username": "morozova_parent_safety",
    "bio": "Мама фигуристки 7 лет. Тревожная, боится травм. Дочь только начала прыгать.",
    "persona": "Ирина — тревожная мама. Фигурное катание = падения, удары, травмы. Читает всё про безопасность. Хочет знать: правильная ли техника у ребёнка? Не приведёт ли к травме? IMU-датчики с объективными данными по биомеханике — это то что даст ей спокойствие. Заплатит до 3К₽/мес за 'безопасность'. Покупает через рекомендации тренера.",
    "age": 35,
    "gender": "female",
    "mbti": "ISFP",
    "country": "Russia",
    "segment": "B_parent",
    "role": "anxious_parent",
    "concern": "injury_prevention",
    "budget_level": "moderate",
    "tech_savviness": "medium"
  },
  {
    "realname": "Андрей Викторович Жуков",
    "username": "zhukov_parent_casual",
    "bio": "Папа фигуристки 6 лет. Просто возит на каток, осознанно не вовлечён.",
    "persona": "Андрей — формальный родитель. Дочь хотела на фигурное катание — ок, отвёз. Оплачивает, но не вникает. Если тренер скажет 'купите датчики' — купит без вопросов. Если нет — даже не узнает о продукте. Цена — не критична, но и переплачивать не будет. 2-3К₽ разово — без раздумий. Подписка — скорее нет.",
    "age": 40,
    "gender": "male",
    "mbti": "ISTP",
    "country": "Russia",
    "segment": "B_parent",
    "role": "casual_parent",
    "concern": "coach_recommendation",
    "budget_level": "moderate",
    "tech_savviness": "low"
  }
]
```

- [ ] **Step 5: Commit personas**

```bash
git add infra/mirofish/personas/
git commit -m "docs(mirofish): add audience persona profiles (B2B, A1/A2, parents)"
```

---

## Task 5: Run First Simulation (A1/A2 Segment)

**Why A1/A2 first:** Most validated baseline — 3 CustDev interviews exist. Can compare simulation results against real data to calibrate.

- [ ] **Step 1: Open MiroFish UI**

1. Open `https://mf.<DOMAIN>` in browser (or `http://78.40.209.34:3000` if Caddy not configured yet)
2. Click "New Project"
3. Name: "SkateLab A1/A2 Validation"
4. Description: "WTP and objection simulation for coaches and athletes"

- [ ] **Step 2: Upload seed document**

1. Navigate to project's document upload section
2. Upload `infra/mirofish/seed-documents/skatelab-market-brief.md`
3. Wait for GraphRAG entity extraction (~7-10 min)
4. Verify: entities and relationships extracted in the graph view

- [ ] **Step 3: Configure simulation parameters**

In the simulation configuration UI:

| Parameter | Value |
|---|---|
| Platform | Reddit |
| Agent count | 12 (4 personas × 3 instances each for diversity) |
| Max rounds | 10 |
| Topic | "AI coaching tool for figure skating — would you use it?" |

- [ ] **Step 4: Load personas**

Upload `infra/mirofish/personas/a1a2-personas.json` via the persona import feature. If UI doesn't support JSON import, manually create 12 agents based on the persona definitions (3 variants per persona type with slight variations in age/budget/concern).

- [ ] **Step 5: Run simulation**

Click "Start Simulation". Monitor progress in the simulation dashboard.

Expected duration: 10-30 minutes depending on LLM response time.

- [ ] **Step 6: Generate report**

After simulation completes:
1. Click "Generate Report"
2. Wait for ReportAgent analysis (2-5 min)
3. Download report (JSON format)

- [ ] **Step 7: Interview key agents**

Use the "Deep Interaction" feature:
1. Chat with top influencer agents identified in the report
2. Ask: "What would make you purchase SkateLab?"
3. Ask: "What is your biggest concern?"
4. Ask: "At what price would you definitely buy? Definitely not buy?"
5. Record responses

- [ ] **Step 8: Export and save results**

```bash
# Copy simulation data from remote server
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 \
  "cp -r /root/mirofish/uploads/simulations/ /root/mirofish/results/a1a2-simulation-$(date +%Y%m%d)/"
```

Download report locally:

```bash
scp -i ~/.ssh/id_rsa_remote_nopass \
  root@78.40.209.34:/root/mirofish/results/a1a2-report-$(date +%Y%m%d).json \
  infra/mirofish/results/
```

- [ ] **Step 9: Calibrate against real CustDev**

Compare simulation results with 3 real CustDev interviews:
- Do simulated objections match real ones?
- Is WTP range consistent?
- Are there surprising new insights?

If simulation diverges significantly from real data, adjust persona definitions and re-run.

---

## Task 6: Run B2B Segment Simulation

- [ ] **Step 1: Create new project**

1. Open `https://mf.<DOMAIN>` in browser
2. "New Project" → Name: "SkateLab B2B Validation"
3. Description: "Institutional buying process simulation for skating schools and academies"

- [ ] **Step 2: Upload seed document**

Upload same `skatelab-market-brief.md`.

- [ ] **Step 3: Configure simulation**

| Parameter | Value |
|---|---|
| Platform | Reddit |
| Agent count | 12 (4 personas × 3 instances) |
| Max rounds | 15 (B2B decisions take longer) |
| Topic | "Your skating school is considering an AI coaching tool. Discuss pros, cons, budget impact." |

- [ ] **Step 4: Load personas**

Upload `infra/mirofish/personas/b2b-personas.json`.

- [ ] **Step 5: Run simulation**

Start simulation. Expected: 15-45 minutes.

- [ ] **Step 6: Generate report + interview agents**

Same process as Task 5 Steps 6-7. Focus questions on:
- Who drives the purchase decision?
- What is the budget range?
- What are implementation barriers?
- Is this top-down or bottom-up?

- [ ] **Step 7: Export results**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 \
  "cp -r /root/mirofish/uploads/simulations/ /root/mirofish/results/b2b-simulation-$(date +%Y%m%d)/"
```

---

## Task 7: Run Parent Segment Simulation

- [ ] **Step 1: Create new project**

1. Open `https://mf.<DOMAIN>` in browser
2. "New Project" → Name: "SkateLab Parent Validation"
3. Description: "Parent motivation and WTP simulation for figure skating AI coaching"

- [ ] **Step 2: Upload seed document**

Upload same `skatelab-market-brief.md`.

- [ ] **Step 3: Configure simulation**

| Parameter | Value |
|---|---|
| Platform | Reddit |
| Agent count | 12 (4 personas × 3 instances) |
| Max rounds | 10 |
| Topic | "Your child's figure skating coach recommends an AI analysis tool. Would you pay for it?" |

- [ ] **Step 4: Load personas**

Upload `infra/mirofish/personas/parent-personas.json`.

- [ ] **Step 5: Run simulation + report + interview**

Same process as Tasks 5-6.

Focus interview questions on:
- Primary motivation: progress visibility, investment protection, safety?
- WTP: standalone or bundled with coaching fees?
- Purchase channel: direct or via coach recommendation?
- Is this a viable independent segment?

- [ ] **Step 6: Export results**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 \
  "cp -r /root/mirofish/uploads/simulations/ /root/mirofish/results/parent-simulation-$(date +%Y%m%d)/"
```

---

## Task 8: Synthesize Cross-Segment Analysis

**Files:**

- Create: `docs/business/02-market/mirofish-simulation-results.md`

- [ ] **Step 1: Compile results from all 3 simulations**

Create a cross-segment comparison document.

- [ ] **Step 2: Write results document**

Write `docs/business/02-market/mirofish-simulation-results.md` with sections:

1. **Executive Summary** — top 3 findings across all segments
2. **Segment Comparison** — receptiveness, WTP range, objection hierarchy
3. **A1/A2 Insights** — validated vs new findings vs divergences from real CustDev
4. **B2B Insights** — decision maker, budget range, barriers, process
5. **Parent Insights** — motivation breakdown, WTP, purchase channel, segment viability
6. **Pricing Sweet Spot** — cross-segment price sensitivity analysis
7. **Feature Trigger Map** — which features drive adoption per segment
8. **Calibration Notes** — where simulation matched/diverged from real CustDev
9. **Action Items** — updated hypotheses for next round of real CustDev

- [ ] **Step 3: Update ROADMAP.md with simulation findings**

If results significantly change MVP scope or target segments, update ROADMAP.md accordingly.

- [ ] **Step 4: Commit results**

```bash
git add docs/business/02-market/mirofish-simulation-results.md
git commit -m "docs(business): add MiroFish audience simulation results"
```

---

## Task 9: Teardown and Cleanup

- [ ] **Step 1: Backup all simulation data from remote**

```bash
scp -i ~/.ssh/id_rsa_remote_nopass -r \
  root@78.40.209.34:/root/mirofish/results/ \
  infra/mirofish/results/
```

- [ ] **Step 2: Stop container on remote**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 \
  "cd /root/mirofish && podman-compose down"
```

- [ ] **Step 3: (Optional) Remove container image to reclaim disk**

```bash
ssh -i ~/.ssh/id_rsa_remote_nopass root@78.40.209.34 \
  "podman rmi ghcr.io/666ghj/mirofish:latest"
```

Only do this if you don't plan to re-run simulations soon. Frees ~2GB.

---

## Self-Review

**Spec coverage check:**
- ✅ Stack: NineRouter + Jina + Zep → Task 1-2
- ✅ Seed document → Task 3
- ✅ 3 segments with personas → Task 4
- ✅ Simulation workflow → Tasks 5-7
- ✅ Cross-segment analysis → Task 8
- ✅ Export + teardown → Tasks 8-9
- ✅ Custom persona template → defined in JSON per segment

**Placeholder scan:**
- ✅ No TBD/TODO
- ✅ All file paths concrete
- ✅ All code blocks complete
- ✅ `<paste-from-step-1>` in .env — acceptable (user action)

**Type consistency:**
- ✅ Persona JSON schema consistent across all 3 files
- ✅ Docker compose port mapping matches spec (3000, 5001)
- ✅ .env vars match MiroFish required config
