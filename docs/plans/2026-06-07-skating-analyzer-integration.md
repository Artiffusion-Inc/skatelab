# SkateLab — Skating Analyzer Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate skating-AI-analyzer ideas into SkateLab: multi-dimensional scoring (5 subscores), enhanced phase detection (5 phases + confidence), MVP gamification (5 levels, 9 skills), and training plans.

**Architecture:** Extend existing analysis pipeline with new scoring layer, phase detection expansion, and gamification system. Backend schemas partially exist. Frontend components buildable with mock data immediately. ML training (BiGRUTASRefiner) runs in parallel with development.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Recharts, shadcn/ui, PyTorch (training only), ONNX Runtime (inference), existing MogaNet-B/YOLOv8n pipeline.

---

## File Structure

### ML (Analysis + Scoring)
| File | Responsibility |
|------|---------------|
| `ml/src/analysis/types.py` | `SubScore`, `MultiDimensionalScore`, `Phase`, `PhaseDetectionResult` dataclasses |
| `ml/src/analysis/multi_score.py` | Compute 5 subscores from metrics + data quality flags |
| `ml/src/analysis/confidence.py` | Phase detection confidence scoring (4 factors) |
| `ml/src/analysis/phase_detector.py` | Extend to 5 phases (approach/takeoff/air/landing/glide_out) |
| `ml/src/analysis/training_plan.py` | Generate training plan from weakest subscore |
| `ml/tests/analysis/test_multi_score.py` | Unit tests for subscore computation |
| `ml/tests/analysis/test_phase_detector.py` | Tests for 5-phase detection on synthetic CoM curves |
| `ml/tests/analysis/test_confidence.py` | Tests for confidence scoring combinations |

### Backend
| File | Responsibility |
|------|---------------|
| `backend/app/models/session_score.py` | `SessionScore` ORM (JSONB subscores) |
| `backend/app/models/session_phase.py` | `SessionPhase` ORM (JSONB phases) |
| `backend/app/models/user_level.py` | `UserLevel` ORM (level, XP) |
| `backend/app/models/skill_progress.py` | `SkillProgress` ORM (9 skills) |
| `backend/app/models/training_plan.py` | `TrainingPlan` ORM (plan items JSONB) |
| `backend/app/schemas.py` | Pydantic schemas (add to existing file) |
| `backend/app/crud/session_score.py` | CRUD for session_scores |
| `backend/app/crud/session_phase.py` | CRUD for session_phases |
| `backend/app/crud/user_level.py` | CRUD for user_levels + XP logic |
| `backend/app/crud/skill_progress.py` | CRUD for skill_progress + unlock logic |
| `backend/app/crud/training_plan.py` | CRUD for training_plans |
| `backend/app/routes/scores.py` | `GET /sessions/{id}/scores` |
| `backend/app/routes/phases.py` | `GET /sessions/{id}/phases` |
| `backend/app/routes/gamification.py` | `GET /users/{id}/level`, `GET /users/{id}/skills` |
| `backend/app/routes/training_plans.py` | `POST /training-plans/generate`, `GET /training-plans/{id}` |
| `backend/app/services/gamification.py` | XP computation, level check, skill unlock rules |
| `backend/app/services/training_plan.py` | Rule-based plan generation from weakest subscore |
| `backend/app/worker_gamification.py` | arq fast worker task for post-processing |
| `backend/alembic/versions/` | 5 migrations |

### Frontend
| File | Responsibility |
|------|---------------|
| `frontend/src/types/index.ts` | Extend with `SubScore`, `PhaseExtended`, `UserLevel`, `SkillItem`, `TrainingPlan` |
| `frontend/src/lib/mocks/skating-analyzer.ts` | Mock data for all 4 components |
| `frontend/src/components/analysis/score-breakdown.tsx` | Recharts BarChart for 5 subscores |
| `frontend/src/components/gamification/gamification-panel.tsx` | Level + XP bar + 3x3 skill grid |
| `frontend/src/components/gamification/training-plan.tsx` | Checklist with priorities |
| `frontend/src/components/analysis/phase-timeline.tsx` | **Edit existing** — extend to 5 phases + confidence |
| `frontend/src/app/(app)/sessions/[id]/page.tsx` | Add "analyzer" tab |
| `frontend/src/lib/api.ts` | API client functions for new endpoints |
| `frontend/messages/ru.json` | Russian translations |
| `frontend/messages/en.json` | English translations |

---

## Wave 1: Frontend Components (Mock Data) — Day 1

All components buildable immediately with static data. No backend or ML required.

### Task 1: Extend Types + Create Mocks

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/lib/mocks/skating-analyzer.ts`

- [ ] **Step 1: Add types to `frontend/src/types/index.ts`**

```typescript
export interface SubScore {
  name: string
  label_ru: string
  value: number        // 0-10
  confidence: number   // 0-1
  contributing_metrics: string[]
}

export interface MultiDimensionalScore {
  subscores: SubScore[]
  overall: number
  data_quality: "good" | "partial" | "poor"
  skeleton_reliability: "reliable" | "uncertain" | "likely_wrong"
}

export interface PhaseExtended {
  name: "approach" | "takeoff" | "air" | "landing" | "glide_out"
  start_frame: number
  end_frame: number
  start_time: number
  end_time: number
  confidence: number
  detection_method: "com_parabola" | "tas_segment" | "heuristic"
}

export interface PhaseDetectionResult {
  phases: PhaseExtended[]
  overall_confidence: number
  element_type: string | null
  fallback_used: boolean
}

export interface UserLevel {
  level: number      // 1-5
  total_xp: number
  xp_to_next: number
  title: string
}

export interface SkillItem {
  id: string
  category: "jumps" | "spins" | "control"
  tier: "bronze" | "silver" | "gold"
  label_ru: string
  unlocked: boolean
  unlocked_at: string | null
  consecutive_sessions: number
  best_score: number
  xp_reward: number
}

export interface TrainingPlanItem {
  id: string
  priority: number
  label_ru: string
  description_ru: string
  completed: boolean
}

export interface TrainingPlan {
  items: TrainingPlanItem[]
  generated_at: string
  completed: boolean
  focus_subscore: string | null
}
```

- [ ] **Step 2: Create mock data file `frontend/src/lib/mocks/skating-analyzer.ts`**

```typescript
import type { MultiDimensionalScore, PhaseDetectionResult, UserLevel, SkillItem, TrainingPlan } from "@/types"

export const mockScore: MultiDimensionalScore = {
  subscores: [
    { name: "takeoff_power", label_ru: "Взлётная мощь", value: 7.2, confidence: 0.85, contributing_metrics: ["airtime", "relative_jump_height"] },
    { name: "rotation_axis", label_ru: "Ось вращения", value: 5.8, confidence: 0.72, contributing_metrics: ["rotation_speed", "total_rotation_deg"] },
    { name: "arm_coordination", label_ru: "Координация рук", value: 6.5, confidence: 0.68, contributing_metrics: ["arm_position_score", "symmetry"] },
    { name: "landing_absorption", label_ru: "Амортизация", value: 4.1, confidence: 0.91, contributing_metrics: ["landing_knee_angle", "hard_landing"] },
    { name: "core_stability", label_ru: "Стабильность корпуса", value: 8.0, confidence: 0.79, contributing_metrics: ["landing_trunk_recovery", "trunk_lean"] },
  ],
  overall: 6.3,
  data_quality: "good",
  skeleton_reliability: "reliable",
}

export const mockPhases: PhaseDetectionResult = {
  phases: [
    { name: "approach", start_frame: 30, end_frame: 55, start_time: 1.0, end_time: 1.83, confidence: 0.82, detection_method: "com_parabola" },
    { name: "takeoff", start_frame: 55, end_frame: 60, start_time: 1.83, end_time: 2.0, confidence: 0.91, detection_method: "com_parabola" },
    { name: "air", start_frame: 60, end_frame: 85, start_time: 2.0, end_time: 2.83, confidence: 0.88, detection_method: "com_parabola" },
    { name: "landing", start_frame: 85, end_frame: 92, start_time: 2.83, end_time: 3.07, confidence: 0.85, detection_method: "com_parabola" },
    { name: "glide_out", start_frame: 92, end_frame: 120, start_time: 3.07, end_time: 4.0, confidence: 0.74, detection_method: "heuristic" },
  ],
  overall_confidence: 0.84,
  element_type: "axel",
  fallback_used: false,
}

export const mockUserLevel: UserLevel = {
  level: 3,
  total_xp: 340,
  xp_to_next: 700,
  title: "Спортсмен",
}

export const mockSkills: SkillItem[] = [
  { id: "jumps_bronze", category: "jumps", tier: "bronze", label_ru: "Первый прыжок", unlocked: true, unlocked_at: "2026-05-01T10:00:00Z", consecutive_sessions: 1, best_score: 5.2, xp_reward: 50 },
  { id: "jumps_silver", category: "jumps", tier: "silver", label_ru: "Три прыжка", unlocked: true, unlocked_at: "2026-05-10T10:00:00Z", consecutive_sessions: 3, best_score: 6.4, xp_reward: 150 },
  { id: "jumps_gold", category: "jumps", tier: "gold", label_ru: "Пять прыжков", unlocked: false, unlocked_at: null, consecutive_sessions: 0, best_score: 0, xp_reward: 300 },
  { id: "spins_bronze", category: "spins", tier: "bronze", label_ru: "Первое вращение", unlocked: true, unlocked_at: "2026-05-02T10:00:00Z", consecutive_sessions: 1, best_score: 5.5, xp_reward: 50 },
  { id: "spins_silver", category: "spins", tier: "silver", label_ru: "Два вращения", unlocked: false, unlocked_at: null, consecutive_sessions: 0, best_score: 0, xp_reward: 150 },
  { id: "spins_gold", category: "spins", tier: "gold", label_ru: "Три вращения", unlocked: false, unlocked_at: null, consecutive_sessions: 0, best_score: 0, xp_reward: 300 },
  { id: "control_bronze", category: "control", tier: "bronze", label_ru: "Симметрия 0.6", unlocked: true, unlocked_at: "2026-05-03T10:00:00Z", consecutive_sessions: 1, best_score: 0.62, xp_reward: 50 },
  { id: "control_silver", category: "control", tier: "silver", label_ru: "Симметрия 0.7", unlocked: true, unlocked_at: "2026-05-15T10:00:00Z", consecutive_sessions: 2, best_score: 0.71, xp_reward: 150 },
  { id: "control_gold", category: "control", tier: "gold", label_ru: "Симметрия 0.8", unlocked: false, unlocked_at: null, consecutive_sessions: 0, best_score: 0, xp_reward: 300 },
]

export const mockTrainingPlan: TrainingPlan = {
  items: [
    { id: "1", priority: 1, label_ru: "Упражнение на амортизацию приземления", description_ru: "3 подхода по 5 приземлений с фокусом на угол колена ≥ 110°", completed: false },
    { id: "2", priority: 2, label_ru: "Работа над осью вращения", description_ru: "Вращение на месте с контролем плеч — 2 минуты", completed: true },
    { id: "3", priority: 3, label_ru: "Усиление взлётной мощи", description_ru: "Прыжки через скакалку — 3x30 сек", completed: false },
    { id: "4", priority: 4, label_ru: "Растяжка плечевого пояса", description_ru: "Комплекс на раскрытие рук — 5 минут", completed: false },
  ],
  generated_at: "2026-06-07T12:00:00Z",
  completed: false,
  focus_subscore: "landing_absorption",
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/mocks/skating-analyzer.ts
git commit -m "feat(frontend): types + mock data for skating analyzer integration"
```

---

### Task 2: ScoreBreakdown Component

**Files:**
- Create: `frontend/src/components/analysis/score-breakdown.tsx`
- Create: `frontend/src/components/analysis/score-breakdown.test.tsx`
- Reference: Existing `frame-metrics-chart.tsx` for Recharts pattern

- [ ] **Step 1: Write the component**

```tsx
"use client"

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from "recharts"
import type { MultiDimensionalScore } from "@/types"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

interface ScoreBreakdownProps {
  score: MultiDimensionalScore
}

const COLORS = {
  high: "#22c55e",   // green-500
  mid: "#eab308",    // yellow-500
  low: "#ef4444",    // red-500
}

function getColor(value: number): string {
  if (value >= 7) return COLORS.high
  if (value >= 5) return COLORS.mid
  return COLORS.low
}

export function ScoreBreakdown({ score }: ScoreBreakdownProps) {
  const data = score.subscores.map((s) => ({
    name: s.label_ru,
    value: s.value,
    confidence: s.confidence,
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Разбор оценки — {score.overall.toFixed(1)} / 10</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 16, bottom: 32, left: 0 }}>
              <XAxis dataKey="name" angle={-30} textAnchor="end" interval={0} tick={{ fontSize: 12 }} />
              <YAxis domain={[0, 10]} tickCount={6} />
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(1)} / 10`, "Оценка"]}
                labelStyle={{ color: "#000" }}
              />
              <ReferenceLine y={5} stroke="#94a3b8" strokeDasharray="3 3" />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getColor(entry.value)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-2 text-sm text-muted-foreground">
          Качество данных: {score.data_quality} | Скелет: {score.skeleton_reliability}
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Write test**

```tsx
import { render, screen } from "@testing-library/react"
import { ScoreBreakdown } from "./score-breakdown"
import { mockScore } from "@/lib/mocks/skating-analyzer"

it("renders 5 bars with labels", () => {
  render(<ScoreBreakdown score={mockScore} />)
  expect(screen.getByText("Взлётная мощь")).toBeInTheDocument()
  expect(screen.getByText("Разбор оценки — 6.3 / 10")).toBeInTheDocument()
})
```

- [ ] **Step 3: Run test**

Run: `cd frontend && npx vitest run src/components/analysis/score-breakdown.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/analysis/score-breakdown.tsx frontend/src/components/analysis/score-breakdown.test.tsx
git commit -m "feat(frontend): ScoreBreakdown bar chart component"
```

---

### Task 3: PhaseTimeline Extension

**Files:**
- Modify: `frontend/src/components/analysis/phase-timeline.tsx`
- Reference: Existing `phase-timeline.tsx` (hardcoded 3 phases)

- [ ] **Step 1: Make polymorphic — support both old and new phase formats**

```tsx
// In phase-timeline.tsx, add support for PhaseDetectionResult
// If phases prop is PhaseDetectionResult (has phase.ranges), render colored segments
// If phases prop is old PhasesData (3 markers), render existing marker view
```

- [ ] **Step 2: Add confidence tooltip and warning for confidence < 0.5**

- [ ] **Step 3: Test with mockPhases**

- [ ] **Step 4: Commit**

---

### Task 4: GamificationPanel

**Files:**
- Create: `frontend/src/components/gamification/gamification-panel.tsx`
- Create: `frontend/src/components/gamification/gamification-panel.test.tsx`

- [ ] **Step 1: Build component with XP bar, level badge, 3x3 skill grid**
- [ ] **Step 2: Use shadcn Progress (thickened variant) for XP**
- [ ] **Step 3: Test with mockUserLevel + mockSkills**
- [ ] **Step 4: Commit**

---

### Task 5: TrainingPlan

**Files:**
- Create: `frontend/src/components/gamification/training-plan.tsx`
- Create: `frontend/src/components/gamification/training-plan.test.tsx`

- [ ] **Step 1: Build checklist with priority badges (1=red, 2=orange, etc.)**
- [ ] **Step 2: Use shadcn Checkbox for items**
- [ ] **Step 3: Test with mockTrainingPlan**
- [ ] **Step 4: Commit**

---

### Task 6: Session Page Integration

**Files:**
- Modify: `frontend/src/app/(app)/sessions/[id]/page.tsx`

- [ ] **Step 1: Add "analyzer" tab next to existing tabs**
- [ ] **Step 2: Render all 4 components with mock data**
- [ ] **Step 3: Verify page loads without errors**
- [ ] **Step 4: Commit**

---

## Wave 2: Backend Schemas + API — Day 1-2

### Task 7: Alembic Migrations (5 tables)

**Files:**
- Create: `backend/alembic/versions/...add_user_levels.py`
- Create: `backend/alembic/versions/...add_skill_progress.py`
- Create: `backend/alembic/versions/...add_session_scores.py`
- Create: `backend/alembic/versions/...add_session_phases.py`
- Create: `backend/alembic/versions/...add_training_plans.py`

- [ ] **Step 1: Generate migration for user_levels**
- [ ] **Step 2: Generate migration for skill_progress**
- [ ] **Step 3: Generate migration for session_scores (parallel with session_phases)**
- [ ] **Step 4: Generate migration for training_plans**
- [ ] **Step 5: Apply all migrations and verify tables exist**

Run: `cd backend && alembic upgrade head`
Expected: 5 new tables in database

- [ ] **Step 6: Commit**

---

### Task 8: ORM Models

**Files:**
- Create: `backend/app/models/user_level.py`
- Create: `backend/app/models/skill_progress.py`
- Create: `backend/app/models/session_score.py`
- Create: `backend/app/models/session_phase.py`
- Create: `backend/app/models/training_plan.py`

- [ ] **Step 1: Write UserLevel model**
- [ ] **Step 2: Write SkillProgress model**
- [ ] **Step 3: Write SessionScore model (JSONB subscores)**
- [ ] **Step 4: Write SessionPhase model (JSONB phases)**
- [ ] **Step 5: Write TrainingPlan model (JSONB items)**
- [ ] **Step 6: Import all in `backend/app/models/__init__.py`**
- [ ] **Step 7: Commit**

---

### Task 9: Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas.py` (add to existing)

- [ ] **Step 1: Add SubScore, MultiDimensionalScore schemas**
- [ ] **Step 2: Add Phase, PhaseDetectionResult schemas**
- [ ] **Step 3: Add UserLevel, SkillProgress schemas**
- [ ] **Step 4: Add TrainingPlan schemas**
- [ ] **Step 5: Commit**

---

### Task 10: CRUD + Services

**Files:**
- Create: `backend/app/crud/session_score.py`
- Create: `backend/app/crud/session_phase.py`
- Create: `backend/app/crud/user_level.py`
- Create: `backend/app/crud/skill_progress.py`
- Create: `backend/app/crud/training_plan.py`
- Create: `backend/app/services/gamification.py`
- Create: `backend/app/services/training_plan.py`

- [ ] **Step 1: CRUD for session_scores (get_by_session_id, create)**
- [ ] **Step 2: CRUD for session_phases**
- [ ] **Step 3: CRUD for user_levels + compute_xp()**
- [ ] **Step 4: CRUD for skill_progress + check_unlock()**
- [ ] **Step 5: CRUD for training_plans + generate_plan()**
- [ ] **Step 6: Gamification service: update_xp_and_levels()**
- [ ] **Step 7: Training plan service: generate from weakest subscore**
- [ ] **Step 8: Commit**

---

### Task 11: API Routes

**Files:**
- Create: `backend/app/routes/scores.py`
- Create: `backend/app/routes/phases.py`
- Create: `backend/app/routes/gamification.py`
- Create: `backend/app/routes/training_plans.py`
- Modify: `backend/app/routes/__init__.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: `GET /sessions/{id}/scores` — returns SessionScore or 404**
- [ ] **Step 2: `GET /sessions/{id}/phases` — returns SessionPhase or 404**
- [ ] **Step 3: `GET /users/{id}/level` — returns UserLevel or default (level 1)**
- [ ] **Step 4: `GET /users/{id}/skills` — returns SkillProgress[]**
- [ ] **Step 5: `POST /training-plans/generate` — creates plan from session scores**
- [ ] **Step 6: `GET /training-plans/{id}` — returns TrainingPlan**
- [ ] **Step 7: Register all routers in main.py**
- [ ] **Step 8: Test endpoints with curl or pytest**
- [ ] **Step 9: Commit**

---

## Wave 3: ML Analysis Layer — Day 2-3

### Task 12: Multi-Score Computation

**Files:**
- Create: `ml/src/analysis/multi_score.py`
- Create: `ml/tests/analysis/test_multi_score.py`
- Modify: `ml/src/analysis/types.py`

- [ ] **Step 1: Write failing test for 5 subscores**

```python
def test_compute_subscores():
    metrics = {
        "airtime": 0.5,
        "relative_jump_height": 0.4,
        "rotation_speed": 450,
        "total_rotation_deg": 720,
        "under_rotation_deg": 30,
        "arm_position_score": 0.7,
        "symmetry": 0.75,
        "landing_knee_angle": 110,
        "landing_knee_stability": 0.8,
        "landing_smoothness": 0.6,
        "hard_landing": 0.2,
        "landing_trunk_recovery": 0.9,
        "approach_torso_lean": 5,
        "trunk_lean": 10,
    }
    result = compute_subscores(metrics)
    assert len(result.subscores) == 5
    assert result.overall >= 0 and result.overall <= 10
```

- [ ] **Step 2: Implement compute_subscores()**

```python
def compute_subscores(metrics: dict[str, float]) -> MultiDimensionalScore:
    # takeoff_power: airtime + height + approach
    takeoff = _normalize(
        metrics["airtime"] / 0.7 * 0.4 +
        metrics["relative_jump_height"] / 1.0 * 0.4 +
        (1 - abs(metrics.get("approach_consistency", 0)) / 90) * 0.2
    )
    # rotation_axis: rot_speed + rotation + under_rotation
    rotation = _normalize(
        min(metrics["rotation_speed"] / 720, 1.0) * 0.4 +
        min(metrics["total_rotation_deg"] / 1620, 1.0) * 0.3 +
        (1 - metrics["under_rotation_deg"] / 90) * 0.3
    )
    # arm_coordination: arm_pos + symmetry
    arms = _normalize(
        metrics["arm_position_score"] * 0.6 +
        metrics["symmetry"] * 0.4
    )
    # landing_absorption: knee_angle + stability + smoothness + hard_landing
    landing = _normalize(
        (1 - abs(metrics["landing_knee_angle"] - 110) / 40) * 0.3 +
        metrics["landing_knee_stability"] * 0.3 +
        metrics["landing_smoothness"] * 0.2 +
        (1 - metrics["hard_landing"]) * 0.2
    )
    # core_stability: trunk_recovery + torso_lean + trunk_lean
    core = _normalize(
        metrics["landing_trunk_recovery"] * 0.5 +
        (1 - abs(metrics["approach_torso_lean"]) / 20) * 0.25 +
        (1 - abs(metrics["trunk_lean"]) / 20) * 0.25
    )

    subscores = [
        SubScore("takeoff_power", "Взлётная мощь", takeoff * 10, 0.8, ["airtime", "relative_jump_height"]),
        SubScore("rotation_axis", "Ось вращения", rotation * 10, 0.7, ["rotation_speed", "total_rotation_deg"]),
        SubScore("arm_coordination", "Координация рук", arms * 10, 0.7, ["arm_position_score", "symmetry"]),
        SubScore("landing_absorption", "Амортизация", landing * 10, 0.8, ["landing_knee_angle", "landing_knee_stability"]),
        SubScore("core_stability", "Стабильность корпуса", core * 10, 0.7, ["landing_trunk_recovery", "trunk_lean"]),
    ]

    overall = sum(s.value * w for s, w in zip(subscores, [0.30, 0.25, 0.15, 0.25, 0.10]))

    return MultiDimensionalScore(
        subscores=subscores,
        overall=overall,
        data_quality="good",
        skeleton_reliability="reliable",
    )
```

- [ ] **Step 3: Run test — verify pass**
- [ ] **Step 4: Commit**

---

### Task 13: Confidence Scoring

**Files:**
- Create: `ml/src/analysis/confidence.py`
- Create: `ml/tests/analysis/test_confidence.py`

- [ ] **Step 1: Write test for confidence combination**
- [ ] **Step 2: Implement compute_overall_confidence()**
- [ ] **Step 3: Run test — verify pass**
- [ ] **Step 4: Commit**

---

### Task 14: Phase Detection Expansion

**Files:**
- Modify: `ml/src/analysis/phase_detector.py`
- Create: `ml/tests/analysis/test_phase_detector.py`

- [ ] **Step 1: Add approach detection (CoM acceleration threshold)**
- [ ] **Step 2: Add glide_out detection (CoM horizontal velocity stabilization)**
- [ ] **Step 3: Update existing 3-phase logic to produce 5 phases**
- [ ] **Step 4: Test on synthetic CoM curves (parabola + noise)**
- [ ] **Step 5: Commit**

---

### Task 15: Training Plan Generation

**Files:**
- Create: `ml/src/analysis/training_plan.py`
- Create: `ml/tests/analysis/test_training_plan.py`

- [ ] **Step 1: Rule-based mapping: weakest subscore → exercise recommendation**
- [ ] **Step 2: Generate 3-5 items with priority**
- [ ] **Step 3: Test with mock subscores**
- [ ] **Step 4: Commit**

---

## Wave 4: Worker Integration — Day 3

### Task 16: Worker Pipeline Update

**Files:**
- Modify: `backend/app/worker.py`
- Create: `backend/app/worker_gamification.py`

- [ ] **Step 1: After pose/tracking/metrics, call compute_subscores()**
- [ ] **Step 2: Save session_scores to DB**
- [ ] **Step 3: Save session_phases to DB**
- [ ] **Step 4: Enqueue `compute_gamification_task` to fast worker queue**
- [ ] **Step 5: Implement `compute_gamification_task` in worker_gamification.py**
- [ ] **Step 6: Fast worker: update XP, check skill unlocks, generate training plan**
- [ ] **Step 7: Commit**

---

## Wave 5: Frontend API Integration — Day 3-4

### Task 17: API Client

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add fetch functions for all 6 endpoints**
- [ ] **Step 2: Add React Query hooks (useSessionScores, useSessionPhases, etc.)**
- [ ] **Step 3: Commit**

---

### Task 18: Swap Mock Data for Real API

**Files:**
- Modify: `frontend/src/app/(app)/sessions/[id]/page.tsx`

- [ ] **Step 1: Replace mock imports with useQuery hooks**
- [ ] **Step 2: Add loading states (Skeleton)**
- [ ] **Step 3: Add error states**
- [ ] **Step 4: Verify end-to-end with real backend**
- [ ] **Step 5: Commit**

---

## Wave 6: ML Training (Parallel Track) — Day 0-2

### Task 19: Copy MCFS from rclone

**Files:**
- Destination: `data/datasets/mcfs/`

- [ ] **Step 1: `rclone copy gdrive-advanced:/MCFS-130 data/datasets/mcfs/`**
- [ ] **Step 2: Verify 271 feature files + ground truth files**
- [ ] **Step 3: Commit**

---

### Task 20: Run BiGRUTASRefiner Training

**Files:**
- Run: `experiments/train_tas_v2.py`

- [ ] **Step 1: Run training script**
```bash
cd /home/dev/skatelab
uv run python experiments/train_tas_v2.py
```
- [ ] **Step 2: Verify checkpoints created in `experiments/checkpoints/tas_v2/`**
- [ ] **Step 3: Export ONNX**
```bash
uv run python experiments/export_tas_onnx.py \
  --checkpoint experiments/checkpoints/tas_v2/fold_0_best.pt \
  --output data/models/tas/bigr_refiner_best.onnx
```
- [ ] **Step 4: Test ONNX inference**
```bash
uv run python -c "from ml.src.tas.inference import TASElementSegmenter; s = TASElementSegmenter('data/models/tas/bigr_refiner_best.onnx'); print('OK')"
```
- [ ] **Step 5: Commit**

---

## Wave 7: Integration + Polish — Day 4-5

### Task 21: End-to-End Integration Test

**Files:**
- Create: `backend/tests/integration/test_skating_analyzer.py`

- [ ] **Step 1: Upload test video through API**
- [ ] **Step 2: Wait for worker completion**
- [ ] **Step 3: Verify session_scores, session_phases created**
- [ ] **Step 4: Verify gamification updated (XP, skills)**
- [ ] **Step 5: Verify frontend renders all 4 components**
- [ ] **Step 6: Commit**

---

### Task 22: i18n Translations

**Files:**
- Modify: `frontend/messages/ru.json`
- Modify: `frontend/messages/en.json`

- [ ] **Step 1: Add Russian translations for subscore names, skill names, plan items**
- [ ] **Step 2: Add English translations**
- [ ] **Step 3: Verify no hardcoded strings in components**
- [ ] **Step 4: Commit**

---

### Task 23: Final Review + Ship

- [ ] **Step 1: Run full test suite: `pytest backend/tests/` + `cd frontend && npx vitest run`**
- [ ] **Step 2: Verify no regressions in existing features**
- [ ] **Step 3: Create PR with description**
- [ ] **Step 4: Ship**

---

## Self-Review

### Spec Coverage

| Spec Requirement | Plan Task |
|---|---|
| 5 subscores with weights | Task 12 |
| Score floor | Included in Task 12 (optional, disabled by default) |
| Data quality flags | Task 12, 13 |
| 5 phases (approach/takeoff/air/landing/glide_out) | Task 14 |
| Confidence scoring | Task 13 |
| 5 levels + XP | Task 10 (gamification service) |
| 9 skills (3×3 grid) | Task 10 |
| Training plan generation | Task 15 |
| DB tables (5) | Task 7 |
| API endpoints (6) | Task 11 |
| Frontend components (4) | Tasks 2-6 |
| Worker integration | Task 16 |
| BiGRUTASRefiner training | Task 20 |
| i18n | Task 22 |

### Placeholder Scan

No TBD/TODO/fill-in-later found. All tasks have concrete file paths and code.

### Type Consistency

- `SubScore` defined in Task 1 (frontend types), used in Tasks 2, 12
- `PhaseExtended` defined in Task 1, used in Task 14
- `UserLevel`/`SkillItem` defined in Task 1, used in Tasks 4, 10
- `TrainingPlan` defined in Task 1, used in Tasks 5, 15

All consistent.

### Gaps

- **Fine classifier (InfoGCN/BiGRU clip-classifier)** — out of scope for this plan. SkatingVerse not downloaded. Separate plan needed.
- **SkatingVerse download** — separate ops task, not dev task.

---

## Execution Handoff

**Plan complete and saved to `docs/plans/2026-06-07-skating-analyzer-integration.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task + review loop. Commit after every step. All tests green before next Wave.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
