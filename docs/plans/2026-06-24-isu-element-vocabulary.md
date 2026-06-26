# ISU Element Vocabulary Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the fragmented 5-system element vocabulary (metrics_registry slug keys, elements_db ISU codes, ML mixed vocabulary, mobile, frontend) to a single canonical ISU code (`3A`, `CSp4`, `StSq4`, `ChSq1`) backed by one backend-owned registry.

**Architecture:** Backend `elements_db.py` extended to the authoritative registry (code + localized names + family + aliases + metadata), exposed via `GET /metrics/elements`. `session.element_type` becomes an ISU code. ML TAS outputs a jump **type** + `phase_detector` counts **rotations**; the worker composes `type + rotations → ISU code` via a remap layer (no TAS retraining). Existing sessions are wiped (dev-stage, no legacy). Mobile/frontend become registry clients via the `elementLabel(key)` seam established by #333.

**Tech Stack:** Python (backend: Litestar, SQLAlchemy, Alembic, arq; ml: numpy, scipy), Kotlin Multiplatform (mobile: Compose), TypeScript/Next.js (frontend: next-intl), Maestro (E2E), pytest.

**Reference spec:** `docs/specs/2026-06-24-isu-element-vocabulary-design.md` — read it first. All decisions below are locked there; do not re-litigate them.

## Global Constraints

- **Backend routes use Litestar** (`Controller`, `@get`/`@post`), NOT FastAPI — despite what root CLAUDE.md says. Follow `backend/app/routes/metrics.py` patterns exactly.
- **Two different `ElementDef` types exist**: `backend/.../elements_db.py` ElementDef (code/name/type/base_value) and `ml/src/...` ElementDef (name/name_ru/rotations/key_joints/ideal_metrics). Do NOT conflate. Backend ElementDef gets extended; ML ElementDef stays as-is (remap reads from backend registry at worker boundary).
- **ISU codes are uppercase, ≤8 chars** (`"3A"`, `"CSp4"`, `"StSq4"`, `"ChSq1"`). DB column stays `String(50)` (no type churn — only values change).
- **No legacy/nullable fallback for element_type.** Decision: wipe. Old `axel`/`toe_loop` sessions are deleted, not mapped.
- **TAS classifier is NOT retrained.** ML outputs coarse type; remap + phase_detector rotations compose the code.
- **Russian terminology is linguistically correct** (Риттбергер not Луп, Лутц not Лютц) — `values-ru/strings.xml` already has correct forms; mirror them in `elements_db.name_ru`.
- **Every user-facing element string resolves through a registry/resource, never a literal** — this is the bug class #331 fixed; the migration must not reintroduce it.
- **GPU-only ML inference** (`device='cuda'`), `bash ml/scripts/setup_cuda_compat.sh` after `uv sync`.
- **Commits on worktree branch only** (Worktree Mandate). Commit format: `<type>(<scope>): <description>`.
- **Spin level detection is explicitly out of scope.** Spins map to base-level codes (`CSp1`, `StSq1`, `ChSq1`); a follow-up issue is opened for spin-level detection. Do not silently approximate levels.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/app/services/choreography/elements_db.py` | Authoritative ISU registry (extend ElementDef: name_ru, name_en, family, aliases) |
| `backend/app/metrics_registry.py` | Metric groups as ISU code tuples (replace slug lists) |
| `backend/app/routes/metrics.py` | Add `GET /elements` registry endpoint |
| `backend/app/schemas.py` | `ElementResponse` schema; `element_type` validation refs ISU |
| `backend/app/worker.py` | Compose ISU code from TAS type + rotations; gamification category from code |
| `ml/src/analysis/isu_remap.py` (new) | `remap_to_isu(type, rotations, registry)`, `ML_TYPE_TO_FAMILY` |
| `ml/src/analysis/phase_detector.py` | Real rotation counting for jumps |
| `ml/src/utils/subtitles.py` | Output ISU code + localized name from registry |
| `backend/alembic/versions/<new>_isu_wipe.py` | Wipe sessions migration |
| `mobile/shared/.../models/ElementLabels.kt` | `elementTypes` → ISU codes (or API-fetched) |
| `mobile/androidApp/.../res/values{,-ru}/strings.xml` | `element_<code>_name` full names |
| `mobile/androidApp/.../ui/elements/ElementTypeBottomSheet.kt` | Group by family; `code — name` |
| `frontend/messages/{ru,en}.json`, `personal-records.tsx`, `rink-figures.tsx` | Registry-fetched ISU-code labels |

---

## Wave 1 — Backend registry (extend `elements_db.py`)

### Task 1: Extend `ElementDef` with localized names, family, aliases

**Files:**
- Modify: `backend/app/services/choreography/elements_db.py:18-45` (ElementDef dataclass + ELEMENTS dict)

**Interfaces:**
- Produces: `ElementDef` with new fields `name_ru: str`, `name_en: str`, `family: str`, `aliases: tuple[str, ...] = ()`; helpers `get_element(code)`, `family_to_isu(family, rotations)`, `ML_TYPE_TO_FAMILY: dict[str,str]`.

- [ ] **Step 1: Write failing test — registry completeness**

Create `backend/tests/test_elements_db.py`:
```python
from app.services.choreography.elements_db import ELEMENTS, get_element, family_to_isu, ML_TYPE_TO_FAMILY

def test_registry_has_localized_names_for_all():
    for code, el in ELEMENTS.items():
        assert el.name_ru, f"{code} missing name_ru"
        assert el.name_en, f"{code} missing name_en"
        assert el.family, f"{code} missing family"

def test_family_to_isu_composes_jump_code():
    assert family_to_isu("A", 3) == "3A"
    assert family_to_isu("T", 1) == "1T"
    assert family_to_isu("Eu", 1) == "1Eu"

def test_ml_type_to_family_covers_tas_vocabulary():
    for tas_type in ["axel","toe_loop","salchow","loop","flip","lutz","waltz_jump","euler"]:
        assert tas_type in ML_TYPE_TO_FAMILY, f"missing TAS type {tas_type}"
    assert ML_TYPE_TO_FAMILY["axel"] == "A"
    assert ML_TYPE_TO_FAMILY["toe_loop"] == "T"
    assert ML_TYPE_TO_FAMILY["waltz_jump"] == "1A"  # waltz = single axel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_elements_db.py -x -q`
Expected: FAIL — fields/functions don't exist yet.

- [ ] **Step 3: Extend `ElementDef` + populate fields**

Modify `elements_db.py` — extend the dataclass:
```python
@dataclass(frozen=True)
class ElementDef:
    code: str
    name: str
    type: ElementType
    base_value: float
    rotations: float = 0.0
    has_toe_pick: bool = False
    entry_edge: str = ""
    exit_edge: str = ""
    combo_eligible: bool = False
    short_program_eligible: bool = True
    name_ru: str = ""
    name_en: str = ""
    family: str = ""
    aliases: tuple[str, ...] = ()
```
Then for each of the 50 elements, populate `name_en` (= existing `name`), `name_ru` (linguistically correct: `1A`→"Одинарный Аксель", `3A`→"Тройной Аксель"; `CSp4`→"Вращение со сменой ноги (комб.) ур.4"; `StSq4`→"Дорожка шагов ур.4"; `ChSq1`→"Хореографическая дорожка"; `1Eu`→"Эйлер (перекидной)"), `family` (`A`/`T`/`S`/`Lo`/`F`/`Lz`/`Eu` for jumps; `family=code` for spins/steps/choreo), and `aliases` for jumps (`("axel",)` on `1A`..`4A`; `("toe_loop",)` on `1T`..`4T`; `("waltz_jump",)` ALSO on `1A` since waltz=1A; `("euler","half_loop")` on `1Eu`).
Add after `ELEMENTS`:
```python
ML_TYPE_TO_FAMILY: dict[str, str] = {
    "axel": "A", "toe_loop": "T", "salchow": "S", "loop": "Lo",
    "flip": "F", "lutz": "Lz", "waltz_jump": "1A", "euler": "Eu", "half_loop": "Eu",
}

def family_to_isu(family: str, rotations: int) -> str | None:
    if family == "1A":  # waltz_jump alias — fixed code
        return "1A"
    return f"{rotations}{family}" if 1 <= rotations <= 4 else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_elements_db.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/choreography/elements_db.py backend/tests/test_elements_db.py
git commit -m "feat(backend): extend elements_db ElementDef with localized names, family, aliases"
```

---

## Wave 2 — Backend API registry endpoint

### Task 2: `GET /metrics/elements` endpoint + schema

**Files:**
- Modify: `backend/app/routes/metrics.py` (add endpoint to `MetricsController`)
- Modify: `backend/app/schemas.py` (add `ElementResponse`)
- Test: `backend/tests/test_metrics_routes.py` (or existing metrics route test file)

**Interfaces:**
- Produces: `GET /metrics/elements` → `{"registry_version": <int>, "elements": [ElementResponse...]}`.

- [ ] **Step 1: Write failing test**

```python
from app.services.choreography.elements_db import ELEMENTS

async def test_get_elements_returns_full_registry(client, auth_headers):
    resp = await client.get("/metrics/elements", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "registry_version" in body
    codes = {e["code"] for e in body["elements"]}
    assert set(ELEMENTS.keys()) <= codes
    axel3 = next(e for e in body["elements"] if e["code"] == "3A")
    assert axel3["name_en"] == "Triple Axel"
    assert axel3["name_ru"]  # localized
    assert axel3["family"] == "A"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd backend && uv run pytest tests/test_metrics_routes.py::test_get_elements_returns_full_registry -x -q`

- [ ] **Step 3: Add schema + endpoint**

In `schemas.py`:
```python
class ElementResponse(BaseModel):
    code: str
    name_ru: str
    name_en: str
    type: str
    family: str
    rotations: float
    base_value: float
```
In `routes/metrics.py`, inside `MetricsController`:
```python
from app.services.choreography.elements_db import ELEMENTS
from app.schemas import ElementResponse

REGISTRY_VERSION = 1

@get("/elements")
async def get_elements(self) -> dict:
    """ISU element registry — canonical codes + localized names."""
    return {
        "registry_version": REGISTRY_VERSION,
        "elements": [
            {
                "code": e.code, "name_ru": e.name_ru, "name_en": e.name_en,
                "type": e.type.value, "family": e.family, "rotations": e.rotations,
                "base_value": e.base_value,
            }
            for e in ELEMENTS.values()
        ],
    }
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/metrics.py backend/app/schemas.py backend/tests/test_metrics_routes.py
git commit -m "feat(backend): GET /metrics/elements registry endpoint"
```

---

## Wave 3 — Backend `metrics_registry` → ISU code groups

### Task 3: Replace slug element lists with ISU code tuples

**Files:**
- Modify: `backend/app/metrics_registry.py:36-52` (JUMP_ELEMENTS/SPIN_ELEMENTS/ALL_ELEMENTS) + all `MetricDef.element_types` references

**Interfaces:**
- Produces: `ALL_JUMPS`, `ALL_SPINS`, `ALL_STEPS`, `ALL_ELEMENTS` as ISU code tuples; `get_metrics_for_element(code)` matches by code.

- [ ] **Step 1: Write failing test**

`backend/tests/test_metrics_registry.py`:
```python
from app.metrics_registry import get_metrics_for_element, ALL_ELEMENTS, METRIC_REGISTRY

def test_jump_metrics_apply_to_isu_jump_codes():
    m = get_metrics_for_element("3A")
    assert "jump_height" in m
    assert "airtime" in m

def test_jump_metrics_do_not_apply_to_spins():
    m = get_metrics_for_element("CSp4")
    assert "jump_height" not in m
    assert "spin_peak_velocity" in m

def test_all_elements_are_isu_codes():
    # No slug remnants like "waltz_jump", "three_turn"
    for code in ALL_ELEMENTS:
        assert code != "three_turn"
        assert code != "waltz_jump"
    # three_turn metrics now under StSq family
    assert "StSq1" in ALL_ELEMENTS

def test_unknown_code_raises():
    import pytest
    with pytest.raises(ValueError):
        get_metrics_for_element("axel")  # old slug, must be rejected
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Replace element group definitions**

In `metrics_registry.py`, replace lines 36-52:
```python
# ISU code families (canonical). Replace slug lists.
AXEL_FAMILY = ("1A", "2A", "3A", "4A")
TOE_LOOP_FAMILY = ("1T", "2T", "3T", "4T")
SALCHOW_FAMILY = ("1S", "2S", "3S", "4S")
LOOP_FAMILY = ("1Lo", "2Lo", "3Lo", "4Lo")
FLIP_FAMILY = ("1F", "2F", "3F", "4F")
LUTZ_FAMILY = ("1Lz", "2Lz", "3Lz", "4Lz")
EULER = ("1Eu",)
JUMP_ELEMENTS = AXEL_FAMILY + TOE_LOOP_FAMILY + SALCHOW_FAMILY + LOOP_FAMILY + FLIP_FAMILY + LUTZ_FAMILY + EULER

SPIN_ELEMENTS = ("CSp1","CSp2","CSp3","CSp4","FSp1","FSp2","FSp3","FSp4",
                 "LSp1","LSp2","LSp3","LSp4","USp1","USp2","USp3","USp4",
                 "CSpB1","CSpB2","CSpB3","CSpB4")
STEP_ELEMENTS = ("StSq1","StSq2","StSq3","StSq4")
CHOREO_ELEMENTS = ("ChSq1",)
# Metrics formerly under "three_turn" (turn technique) now apply to step sequences:
TURN_METRIC_ELEMENTS = STEP_ELEMENTS
ALL_ELEMENTS = JUMP_ELEMENTS + SPIN_ELEMENTS + STEP_ELEMENTS + CHOREO_ELEMENTS
```
Then update every `MetricDef.element_types`:
- jump metrics (`airtime`, `jump_height`, `rotation`, etc.): `JUMP_ELEMENTS`
- spin metrics (`spin_type`, `spin_peak_velocity`): `SPIN_ELEMENTS`
- turn/edge metrics (`pre_rotation`, `trunk_lean`, `edge_change_smoothness`, `spread_eagle_angle`, `ina_bauer_score`, `spiral_indicator`): `TURN_METRIC_ELEMENTS` (was `("three_turn",)`)
- `rotation_discrepancy`: `(*JUMP_ELEMENTS, *SPIN_ELEMENTS)`
- `estimated_score`: `(*JUMP_ELEMENTS, *SPIN_ELEMENTS, *STEP_ELEMENTS)`
- `symmetry`: `ALL_ELEMENTS`
Update `get_metrics_for_element` docstring to reference ISU codes.

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/metrics_registry.py backend/tests/test_metrics_registry.py
git commit -m "feat(backend): metrics_registry ISU code element groups"
```

---

## Wave 4 — ML remap layer + rotation counting

### Task 4: `isu_remap.py` remap function

**Files:**
- Create: `ml/src/analysis/isu_remap.py`
- Test: `ml/tests/test_isu_remap.py`

**Interfaces:**
- Produces: `remap_to_isu(tas_type: str, rotations: int) -> str | None`.

- [ ] **Step 1: Write failing test**

`ml/tests/test_isu_remap.py`:
```python
from src.analysis.isu_remap import remap_to_isu

def test_jump_type_and_rotations_compose_code():
    assert remap_to_isu("axel", 3) == "3A"
    assert remap_to_isu("toe_loop", 1) == "1T"
    assert remap_to_isu("lutz", 4) == "4Lz"

def test_waltz_jump_is_single_axel():
    assert remap_to_isu("waltz_jump", 1) == "1A"  # rotations ignored for waltz

def test_unknown_type_returns_none():
    assert remap_to_isu("unknown_thing", 3) is None

def test_invalid_rotations_returns_none():
    assert remap_to_isu("axel", 0) is None  # can't have 0-rotation jump
    assert remap_to_isu("axel", 5) is None
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd ml && uv run pytest tests/test_isu_remap.py -x -q`

- [ ] **Step 3: Implement `isu_remap.py`**

```python
"""Remap ML TAS coarse output + phase_detector rotations to canonical ISU code.

ML is NOT retrained (decision: remap layer, not retraining). The TAS classifier
emits a jump type slug; phase_detector counts rotations. This composes the ISU
code via the shared ML_TYPE_TO_FAMILY map (mirrors backend elements_db.aliases).
"""
from __future__ import annotations

# Must stay in sync with backend/app/services/choreography/elements_db.py ML_TYPE_TO_FAMILY.
ML_TYPE_TO_FAMILY: dict[str, str] = {
    "axel": "A", "toe_loop": "T", "salchow": "S", "loop": "Lo",
    "flip": "F", "lutz": "Lz", "waltz_jump": "1A", "euler": "Eu", "half_loop": "Eu",
}

def remap_to_isu(tas_type: str, rotations: int) -> str | None:
    family = ML_TYPE_TO_FAMILY.get(tas_type)
    if family is None:
        return None
    if family == "1A":  # waltz_jump — fixed single axel code
        return "1A"
    if not 1 <= rotations <= 4:
        return None
    return f"{rotations}{family}"
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**

```bash
git add ml/src/analysis/isu_remap.py ml/tests/test_isu_remap.py
git commit -m "feat(ml): isu_remap composes ISU code from TAS type + rotations"
```

### Task 5: `phase_detector` real rotation counting for jumps

**Files:**
- Modify: `ml/src/analysis/phase_detector.py` (jump phase detection path; currently `rotations=0` placeholder)
- Test: `ml/tests/test_phase_detector.py`

**Note:** The jump phase detector must integrate the rotation-angle trajectory over the flight phase and round to the nearest integer (1-4). This reuses existing phase boundary detection (takeoff/landing). If the existing jump path does not yet compute a rotation angle, add a helper that integrates angular velocity (shoulder/hip orientation delta) across flight frames → full turns → `int(round(turns))`.

- [ ] **Step 1: Write failing test — synthetic rotation trajectory**

```python
import numpy as np
from src.analysis.phase_detector import count_rotations

def test_count_rotations_from_flight_trajectory():
    # 3 full turns over flight window → 3
    angles = np.linspace(0, 3 * 2 * np.pi, 60)
    assert count_rotations(angles) == 3

def test_count_rotations_zero_for_short():
    angles = np.linspace(0, 0.3 * 2 * np.pi, 30)  # <1 turn
    assert count_rotations(angles) == 0
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement `count_rotations`**

In `phase_detector.py`:
```python
def count_rotations(angles: np.ndarray) -> int:
    """Full turns over a flight-phase angle trajectory (radians), rounded."""
    total = float(np.abs(angles[-1] - angles[0])) / (2 * np.pi)
    return int(round(total))
```
Wire it into the jump phase detector so the result populates `ElementPhase` / the analyzer output instead of `rotations=0`.

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**

```bash
git add ml/src/analysis/phase_detector.py ml/tests/test_phase_detector.py
git commit -m "feat(ml): phase_detector counts jump rotations from flight trajectory"
```

---

## Wave 5 — Worker ISU composition + gamification category

### Task 6: Worker composes ISU code; gamification category from code

**Files:**
- Modify: `backend/app/worker.py:484` (where `analyzer["element_type"]` flows in) and `:817-829` (gamification category matching)
- Test: `backend/tests/test_worker_isu_compose.py`

- [ ] **Step 1: Write failing test**

```python
def test_worker_composes_isu_code_from_tas_and_rotations():
    # TAS says "axel", phase_detector says 3 → session.element_type = "3A"
    code = compose_isu_element_type(tas_type="axel", rotations=3)
    assert code == "3A"

def test_worker_unknown_tas_stores_none():
    assert compose_isu_element_type(tas_type="garbage", rotations=3) is None

def test_gamification_category_from_isu_code():
    from app.worker import _category_for_element
    assert _category_for_element("3A") == "jumps"
    assert _category_for_element("CSp4") == "spins"
    assert _category_for_element("StSq2") == "control"
    assert _category_for_element(None) is None
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Wire remap into worker**

In `worker.py`, add:
```python
from app.services.choreography.elements_db import get_element

def compose_isu_element_type(tas_type: str | None, rotations: int | None) -> str | None:
    if not tas_type or rotations is None:
        return None
    # import ml remap lazily to avoid importing ML pipeline at module load
    from src.analysis.isu_remap import remap_to_isu  # type: ignore
    return remap_to_isu(tas_type, rotations)

def _category_for_element(code: str | None) -> str | None:
    if not code:
        return None
    el = get_element(code)
    if el is None:
        return None
    if el.type.value == "jump":
        return "jumps"
    if el.type.value == "spin":
        return "spins"
    return "control"  # step / choreo sequences
```
Replace the `element_type.lower()` / `"spin" in et` block at line 825-829 with `category = _category_for_element(element_type)`.
At line 484 (`element_type=analyzer["element_type"]`), route through `compose_isu_element_type(analyzer["element_type"], analyzer.get("rotations"))` and store the ISU code.

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker.py backend/tests/test_worker_isu_compose.py
git commit -m "feat(backend): worker composes ISU code; gamification category from code"
```

---

## Wave 6 — Alembic wipe migration

### Task 7: Wipe sessions migration

**Files:**
- Create: `backend/alembic/versions/<rev>_isu_element_wipe.py`

- [ ] **Step 1: Generate migration**

```bash
cd backend && uv run alembic revision -m "isu element_type wipe"
```

- [ ] **Step 2: Write migration body**

```python
"""isu element_type wipe

Revision ID: <auto>
"""
from alembic import op

def upgrade() -> None:
    # Dev-stage: no production users. Old element_type slugs (axel/toe_loop) carry
    # no rotation level and cannot map unambiguously to ISU codes. Wipe, do not backfill.
    op.execute("DELETE FROM session_metrics;")
    op.execute("DELETE FROM session_elements;")
    op.execute("DELETE FROM session_phases;")
    op.execute("DELETE FROM sessions;")
    # element_type column stays String(50) — only values change to ISU codes (<=8 chars).

def downgrade() -> None:
    # No downgrade: wiped data is unrecoverable. Dev-stage accepted.
    pass
```

- [ ] **Step 3: Apply + verify**

Run: `cd backend && uv run alembic upgrade head && uv run python -c "import asyncio; from app.database import async_session_factory; from sqlalchemy import text; ..." # assert sessions count == 0`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(backend): alembic migration wipe sessions for ISU element_type"
```

---

## Wave 7 — Mobile (builds on #333 seam)

### Task 8: Mobile element catalog → ISU codes

**Files:**
- Modify: `mobile/shared/.../models/ElementLabels.kt` (`elementTypes` list)
- Modify: `mobile/androidApp/.../res/values/strings.xml` + `values-ru/strings.xml`
- Modify: `mobile/androidApp/.../ui/elements/ElementTypeBottomSheet.kt` (family grouping)
- Test: `mobile/shared/src/commonTest/.../models/SerializationTest.kt` (update `elementTypes_*`)

**Note:** The `elementLabel(key)` composable from #333 is REUSED unchanged — only the set of keys changes from `axel`/... to ISU codes. The picker groups by family (Axel → 1A/2A/3A/4A).

- [ ] **Step 1: Update `elementTypes` test to expect ISU codes**

In `SerializationTest.kt`:
```kotlin
@Test
fun elementTypes_containsExpectedIsuCatalog() {
    assertEquals(
        listOf("1A","2A","3A","4A","1T","2T","3T","4T","1S","2S","3S","4S",
               "1Lo","2Lo","3Lo","4Lo","1F","2F","3F","4F","1Lz","2Lz","3Lz","4Lz","1Eu",
               "CSp1","CSp2","CSp3","CSp4","StSq1","StSq2","StSq3","StSq4","ChSq1"),
        elementTypes,
    )
}
```

- [ ] **Step 2: Run shared test, verify FAIL** (`./gradlew :shared:testDebugUnitTest`)

- [ ] **Step 3: Update `ElementLabels.kt` `elementTypes` to ISU codes**

Replace the slug list with the ISU code list above (matching the test). Keep `elementLabel(key)` helper as-is.

- [ ] **Step 4: Add string resources for ISU full names**

In both `values/strings.xml` and `values-ru/strings.xml`, add per-code full-name entries:
```xml
<string name="element_3A_name">Triple Axel</string>   <!-- en -->
<!-- values-ru: -->
<string name="element_3A_name">Тройной Аксель</string>
```
…and update `elementLabel()` in `ElementLabels.kt` to resolve `element_<code>_name` (the code itself, e.g. `"3A"`, is locale-agnostic and shown verbatim alongside).

- [ ] **Step 5: Picker family grouping in `ElementTypeBottomSheet.kt`**

Group `elementTypes` by family letter (`A`, `T`, `S`, `Lo`, `F`, `Lz`, `Eu`, plus spin/step/choreo groups). Render each family as a header (e.g. "Axel") with the rotation variants as options. User taps a family; the detected rotation (from last analysis or manual override) fills the code. **Detail left to implementer** — confirm the family-grouping UX works with a Maestro flow in Wave 9.

- [ ] **Step 6: Build + run android tests**

Run (Docker fallback if daemon flaky): `docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local ./gradlew :shared:testDebugUnitTest :androidApp:testDebugUnitTest ktlintCheck --no-daemon --no-configuration-cache`

- [ ] **Step 7: Commit**

```bash
git add mobile/
git commit -m "feat(mobile): element catalog ISU codes + family-grouped picker"
```

---

## Wave 8 — Frontend registry client

### Task 9: Frontend ISU-code labels from registry

**Files:**
- Modify: `frontend/messages/ru.json` + `en.json` (element block → ISU-code keys)
- Modify: `frontend/src/components/profile/personal-records.tsx` (group by ISU code)
- Modify: `frontend/src/hooks/use-metric-registry.ts` (fetch `/metrics/elements` alongside registry)
- Test: `frontend/src/components/profile/__tests__/personal-records.test.tsx` (or existing)

- [ ] **Step 1: Write failing test — PR grouped by ISU code label**

```tsx
it("groups personal records by ISU element label", () => {
  const prs = [{ element_type: "3A", value: 0.85, session_id: "s1" }];
  render(<PersonalRecords prs={prs} registry={ISU_REGISTRY_FIXTURE} />);
  expect(screen.getByText("3A — Triple Axel")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run, verify FAIL** (`bun run test`)

- [ ] **Step 3: Fetch registry + ISU-code labels**

In `use-metric-registry.ts`, also fetch `GET /metrics/elements` and expose a `elements: Record<code, {name_ru, name_en, family}>` map. In `personal-records.tsx`, replace `te(elementType)` slug lookup with `t(\`element.${code}_name\`)` (registry-backed) and render `"{code} — {name}"`.

- [ ] **Step 4: Replace `messages/{ru,en}.json` element block**

Replace `waltz_jump`/`toe_loop`/... keys with `element.3A_name` etc. (mirror mobile string resources).

- [ ] **Step 5: Run fe-typecheck + fe-test + fe-build**

Run: `cd frontend && bun run typecheck && bun run test && bun run build`

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): ISU-code element labels from registry"
```

---

## Wave 9 — E2E + follow-up issue

### Task 10: Update Maestro flow + verify ISU storage end-to-end

**Files:**
- Modify: `mobile/e2e/maestro/flows/upload-pipeline.yaml` (selector `"axel"` → `"3A"` or family picker)

- [ ] **Step 1: Update flow selector**

In `upload-pipeline.yaml` steps 42-43, replace `tapOn: "axel"` with the new family-picker target (e.g. `tapOn: "Axel"` then `tapOn: "3A"`, per the Wave 7 picker UX).

- [ ] **Step 2: Build APK + run Maestro on `skatelab-emulator`**

```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local ./gradlew :androidApp:assembleDebug --no-daemon
docker cp mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk skatelab-emulator:/tmp/app.apk
docker exec skatelab-emulator adb uninstall ru.skatelab.capture
docker exec skatelab-emulator adb install /tmp/app.apk
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/upload-pipeline.yaml
```
Expected: element selection succeeds (ISU picker), session-detail shows `"3A — Triple Axel"` (en locale).

- [ ] **Step 3: Commit + verify session.element_type in DB**

After a successful upload+process, query the session: `element_type` must be `"3A"` (or the detected code), not `axel`.

```bash
git add mobile/e2e/maestro/flows/upload-pipeline.yaml
git commit -m "test(mobile-e2e): upload-pipeline ISU element picker"
```

### Task 11: Open follow-up issue — spin level detection

- [ ] **Step 1: Open issue**

```bash
gh issue create --repo Artiffusion-Inc/skatelab \
  --title "Spin level detection (CSp1 vs CSp4) — ISU follow-up" \
  --body "ISU element vocabulary migration (PR <this>) maps spins to base-level codes (CSp1, StSq1, ChSq1) because no spin-level detector exists yet. This issue tracks adding a spin-level classifier so spins get their true ISU level. Out of scope for the vocabulary migration." \
  --label "enhancement"
```

---

## Self-Review Checklist (run before handing off)

- [ ] Spec coverage: every section in `docs/specs/2026-06-24-isu-element-vocabulary-design.md` maps to a Wave above (registry=W1, endpoint=W2, metrics=W3, ML remap+rotations=W4, worker=W5, migration=W6, mobile=W7, frontend=W8, E2E+follow-up=W9).
- [ ] No placeholders: all code blocks contain real code/signatures.
- [ ] Type consistency: `remap_to_isu` / `compose_isu_element_type` / `ML_TYPE_TO_FAMILY` names match across W4/W5; `family_to_isu` consistent W1.
- [ ] `ML_TYPE_TO_FAMILY` defined in TWO places (backend `elements_db.py` + ml `isu_remap.py`) — spec acknowledges this; a future cleanup could expose backend as source. Flagged but acceptable (ML must not import backend at runtime).
- [ ] Spin-level detection explicitly deferred (Task 11) — no silent approximation.