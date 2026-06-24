# ISU Element Vocabulary — Unified Canonical Design

> **Status:** Design spec (for delegation). Pre-implementation.
> **Author:** brainstorming session 2026-06-24.
> **Resolves:** the fragmented element-naming problem underlying #331 (and the broader 5-system terminology drift it surfaced).
> **Prerequisite merged:** PR #333 (i18n display fix — established the `elementLabel(key)` UI seam this migration builds on).

## Problem

Figure-skating element identity exists today as **five conflicting, overlapping vocabularies** across the stack, none canonical:

| System | File | Vocabulary | Has level/обороты? |
|--------|------|-----------|-------------------|
| Backend scoring | `backend/app/metrics_registry.py:37-52` | `waltz_jump`/`toe_loop`/`flip`/`salchow`/`loop`/`lutz`/`axel` (7 jumps) + `three_turn` + `upright_spin`/`one_foot_spin`/`scratch_spin` | No |
| Backend choreography | `backend/app/services/choreography/elements_db.py` | **Full ISU DB** (50 codes: `1A`-`4A`, `1Eu`, `CSp1-4`, `FSp1-4`, `LSp1-4`, `USp1-4`, `CSpB1-4`, `StSq1-4`, `ChSq1`) per ISU Comm 2707 | **Yes** (`rotations`, `base_value`) |
| ML recommender | `ml/src/analysis/recommender.py:127-134` | jump-type keys (`axel`/`salchow`/...) + `three_turn` | No |
| ML phase/segmenter/subtitles | `ml/src/analysis/phase_detector.py`, `element_segmenter.py`, `utils/subtitles.py:36+` | mixed — jump types + extended spins/steps (`sit_spin`, `biellmann_spin`, `mohawk`, `choctaw`, `double_three_turn`, `rittberger`...) | No |
| Mobile (post-#333) | `mobile/shared/.../models/ElementLabels.kt` (`elementTypes`) + `strings.xml` | `axel`/`toe_loop`/... + `three_turn`/`spin` | No |
| Frontend | `frontend/messages/ru.json:302-308` + `rink-figures.tsx:19-24` | `waltz_jump`/`toe_loop`/... with **different ru names** (Тулуп↔Перекидной), `rink-figures` already parses ISU base letter | No (frontend) / partial (`rink-figures`) |

Consequences: (1) the same jump is shown as "Аксель"/"Тулуп"/"Перекидной"/"Риттбергер" depending on surface; (2) **no rotation count** anywhere in the scoring path — a 3A and a 1A are indistinguishable in `session.element_type`, so PRs/trends/metrics conflate them; (3) `elements_db.py` already has the full ISU model but it's siloed to the choreography planner and never feeds scoring/ML/mobile.

## Goal

Make the **ISU code** (`3A`, `3T`, `CSp4`, `StSq4`, `ChSq1`) the single canonical element identity across the entire stack — backend, ML, mobile, frontend — with one backend-owned registry as the source of truth for codes, localized display names, and metadata (rotations, base value, type).

## Decisions (locked in brainstorming)

1. **Scope: full unified ISU everywhere.** Canonical key = ISU code in `session.element_type`, metrics matching, ML output remap, mobile picker, frontend labels. No parallel legacy vocabulary.
2. **Single registry: backend `elements_db.py` extended** to the authoritative source (code + `name_ru` + `name_en` + type + rotations + base_value), exposed via API. Mobile/frontend/ML are clients, never owners.
3. **Data migration: wipe.** Existing `session.element_type` rows (dev-stage, `axel`/`toe_loop` without level) cannot be unambiguously mapped to ISU (axel→1A? 3A?) and would distort PRs/trends. **Delete all existing sessions** rather than carry legacy/noise. No nullable fallback field, no dual contract. (User decision: "можешь вообще вайпнуть записи в бд, не нужно legacy костыли".)
4. **ML TAS: remap layer, no retraining.** The TAS coarse classifier (4 classes None/Jump/Spin/Step) and the fine RF classifier (top-30) are NOT retrained — retraining needs new ISU-labeled data and is out of scope. ML outputs a jump **type** (`axel`/`salchow`/...) and the **rotation count** comes from `phase_detector` (already estimates rotations from CoM/rotation trajectory — `phase_detector.py:442` currently sets `rotations=0`; this task makes it count). The worker composes `type + rotations → ISU code` (`axel` + 3 → `3A`) via a remap function backed by the registry.
5. **API/DB contract: `element_type = ISU String(8)`** (e.g. `"3A"`, `"CSp4"`). Metrics match by ISU code via registry groups (e.g. `jump_height.metric.element_types = ["1A","2A","3A","4A"]`). New `GET /metrics/elements` returns the full registry; mobile/frontend cache it at startup.
6. **Rotation source: `phase_detector`** counts rotations from CoM/rotation trajectory (reuses existing phase infrastructure). TAS gives type, phase_detector gives rotations, worker composes the full code. User does NOT pick rotation manually (auto-detected), but **does pick the element type** in the mobile picker (which lists ISU jump families, e.g. "Axel", then the detected rotation fills the level).

## Architecture

```
                  ┌─────────────────────────────────────────┐
                  │  backend elements_db.py (source of truth)│
                  │  ELEMENTS: {code: ElementDef(code,        │
                  │    name_ru, name_en, type, rotations,      │
                  │    base_value, ...)}                       │
                  └───────────────┬───────────────────────────┘
                                  │ GET /metrics/elements (cached)
            ┌─────────────────────┼──────────────────────┐
            ▼                     ▼                      ▼
       Mobile picker          Frontend labels         ML remap layer
       (elementLabel(code))   (t(code) from registry)  (worker, see below)
            │                     │
            ▼                     ▼
       POST /sessions.init (element_type = "3A")
            │
            ▼
   session.element_type String(8) = "3A"   ←── canonical, stored
            │
            ▼
   arq worker → ML pipeline:
     TAS classifier → type = "axel" (coarse)
     phase_detector → rotations = 3
     worker.remap_to_isu(type, rotations, registry) → "3A"
     writes session.element_type = "3A"
     metrics_registry matches "3A" → jump_height metric applies
```

### Registry (extend `elements_db.py`)

Current `ElementDef` has `code, name, type, base_value, rotations, has_toe_pick, entry_edge, exit_edge, combo_eligible, short_program_eligible`. Extend:
- Add `name_ru: str` and `name_en: str` (replace single `name`). For spins/steps that already have English names like "Change Foot Combination Spin Lv1", `name_en` = that, `name_ru` = "Вращение со сменой ноги (комб.) ур.1".
- Add a `family: str` field — the jump family without rotation (`"A"`, `"T"`, `"S"`, `"Lo"`, `"F"`, `"Lz"`, `"Eu"`), so the mobile picker can group `1A/2A/3A/4A` under "Axel". For spins/steps, `family = code`.
- Add `aliases: tuple[str, ...]` for ML remap input (`axel`→`"A"`, `toe_loop`→`"T"`, `salchow`→`"S"`, `loop`→`"Lo"`, `flip`→`"F"`, `lutz`→`"Lz"`, `waltz_jump`→`"1A"` (waltz = single axel, half-rotation), `euler`/`half_loop`→`"Eu"`). This is the bridge from the old ML vocabulary to ISU family letters.

Expose:
- `GET /metrics/elements` → `{elements: [{code, name_ru, name_en, type, family, rotations, base_value}]}`. Public, cacheable.
- Internal helpers: `get_element(code)`, `get_jumps()`, `get_spins()`, `family_to_isu(family, rotations)`.

### metrics_registry

`JUMP_ELEMENTS` etc. become **ISU code lists**, not string-typed slugs:
```python
AXEL_FAMILY = ("1A", "2A", "3A", "4A")
TOE_LOOP_FAMILY = ("1T", "2T", "3T", "4T")
# ... etc
ALL_JUMPS = AXEL_FAMILY + TOE_LOOP_FAMILY + ...  # all 1*-4* + 1Eu
SPIN_ELEMENTS = ("CSp1",...,"CSp4", "FSp1",...,"USp4", "CSpB1",...,"CSpB4", "LSp1",...,"LSp4")
STEP_ELEMENTS = ("StSq1","StSq2","StSq3","StSq4")
ALL_ELEMENTS = ALL_JUMPS + SPIN_ELEMENTS + STEP_ELEMENTS + ("ChSq1",)
```
`MetricDef.element_types` references these codes. `jump_height` applies to `ALL_JUMPS`; `airtime` to `ALL_JUMPS`; spin-specific metrics to `SPIN_ELEMENTS`. Metrics filter `Session.element_type IN (...)`.

### ML remap layer

New `ml/src/analysis/isu_remap.py` (or in worker):
```python
def remap_to_isu(tas_type: str, rotations: int, registry) -> str | None:
    # tas_type in {"axel","toe_loop","salchow","loop","flip","lutz","waltz_jump","euler", spin/step markers}
    family = ML_TYPE_TO_FAMILY.get(tas_type)  # "axel"->"A", "toe_loop"->"T", ...
    if family is None:
        return None  # unknown / not a jump
    # waltz_jump is a 1.5-rotation axel = 1A; euler = 0.5 = 1Eu
    return f"{rotations}{family}"  # rotations from phase_detector (int, 1..4)
```
- `phase_detector.py`: replace the `rotations=0` placeholder with actual rotation counting from the rotation-angle trajectory (integrate angular velocity / count full turns in the flight phase). Output `rotations: int`.
- `worker.py:817-829`: where `element_type.lower()` is currently matched against the old slug list, call `remap_to_isu(...)` and store the ISU code in `session.element_type`.
- Spins/steps: TAS coarse class → ISU family (e.g. "spin" → best-matching `CSp4` by level from `phase_detector` rotation count, or default `CSp1`). Level detection for spins is a separate, harder problem — **scope note**: this spec defines jump remap precisely; spin/step level detection is left as "map to base-level code (`CSp1`/`StSq1`/`ChSq1`) until a spin-level detector exists", explicitly noted as follow-up (no silent approximation).

### Mobile (builds on PR #333 seam)

`ElementLabels.kt` `elementTypes` list becomes the **ISU code list** (or fetched from `/metrics/elements` and cached). `elementLabel(code)` resolves `element_<code>` string resources — but ISU codes are locale-agnostic (`"3A"` displays as `"3A"` everywhere; the **full name** "Triple Axel"/"Тройной Аксель" is the localized part). So:
- `strings.xml`: `element_3A_name` = "Triple Axel" (en) / "Тройной Аксель" (ru). Code itself shown alongside: `"3A — Triple Axel"`.
- Picker groups by family: "Axel" group → `[1A, 2A, 3A, 4A]`. User taps the family, then (auto-detected) rotation determines the code; OR user picks full code directly (decision: user picks family, rotation auto-filled from last analysis or manual override). **Open UI detail** — left to the implementation plan; the spec only fixes that the stored value is the full ISU code.
- Existing `elementLabel(key)` helper from #333 is reused unchanged — only the set of keys changes from `axel`/... to `1A`/...

### Frontend

`frontend/messages/ru.json` element block (`waltz_jump`/...) → replaced by ISU-code-keyed entries, fetched from `/metrics/elements` (same registry). `rink-figures.tsx:19-24` already parses ISU base letter — keep, now it's the canonical path. `personal-records.tsx` groups by `element_type` = ISU code; display `t(code)` resolves via registry.

### Data migration

Alembic migration:
1. `DELETE FROM sessions;` (and dependent `session_metrics`, `session_elements`, `session_phases` via cascade) — wipe, per decision 3. Dev-stage data, no production users yet.
2. `ALTER TABLE sessions ALTER COLUMN element_type TYPE VARCHAR(8);` (already `String(50)`, shrink to `8` for ISU codes; or keep `String(50)` to avoid a wide migration — **decision: keep `String(50)`**, the length is irrelevant, only the values change; avoid unnecessary type churn).
3. Drop/replace any enum constraints (none currently — it's a free `String`).

No backfill. New sessions get ISU codes from the worker.

## Components / File Impact

| Layer | File | Change |
|-------|------|--------|
| Backend registry | `backend/app/services/choreography/elements_db.py` | Add `name_ru`, `name_en`, `family`, `aliases` to `ElementDef`; populate for all 50 elements; add `family_to_isu()`, `ML_TYPE_TO_FAMILY` map |
| Backend metrics | `backend/app/metrics_registry.py` | `JUMP_ELEMENTS`/`SPIN_ELEMENTS`/`ALL_ELEMENTS` → ISU code tuples; update all `MetricDef.element_types` |
| Backend API | `backend/app/routes/metrics.py` (or new `elements.py`) | `GET /metrics/elements` returning the registry |
| Backend schemas | `backend/app/schemas.py` | `element_type` docs/validation reference ISU codes; add `ElementResponse` schema |
| Backend worker | `backend/app/worker.py:817-829,484` | Call `remap_to_isu(tas_type, rotations, registry)`; store ISU code |
| ML remap | `ml/src/analysis/isu_remap.py` (new) | `remap_to_isu()`, `ML_TYPE_TO_FAMILY` |
| ML phase | `ml/src/analysis/phase_detector.py:442` | Real rotation counting (integrate angular velocity over flight phase → int) |
| ML subtitles | `ml/src/utils/subtitles.py:36+` | `ELEMENT_NAMES_RU` map → output ISU code + localized name from registry |
| Mobile shared | `mobile/shared/.../models/ElementLabels.kt` | `elementTypes` → ISU codes (or fetch from API); `elementLabel(code)` unchanged |
| Mobile strings | `mobile/androidApp/.../res/values{,-ru}/strings.xml` | `element_3A_name` etc. (full names per code); code displayed verbatim |
| Mobile picker | `mobile/androidApp/.../ui/elements/ElementTypeBottomSheet.kt` | Group by family; show `code — name` |
| Frontend | `frontend/messages/{ru,en}.json`, `personal-records.tsx`, `rink-figures.tsx` | ISU-code-keyed labels from registry; display groups |
| Migration | `backend/alembic/versions/<new>_isu_element_type.py` | Wipe sessions; (length unchanged) |

## Error Handling

- **Unknown ML type**: `remap_to_isu` returns `None` → worker stores `session.element_type = None` (nullable already) and marks session with a warning finding ("element not recognized"). Do not store a guessed code.
- **Rotation count failure**: `phase_detector` returns `rotations=0` or uncertain → if type is a jump family but rotations==0, store `None` + finding ("could not determine rotation count"). Better null than wrong level.
- **Registry fetch failure (mobile/frontend)**: cache last-known-good registry; if empty, fall back to a bundled static snapshot of the 50 codes (shipped in the app) so the picker never breaks. Invalidate cache on registry version bump (add `registry_version` to the endpoint).
- **Metric matching with unknown code**: `metrics_registry` lookup misses → metric simply doesn't apply (already the behavior); no crash.

## Testing

- **Backend**: `test_elements_db` — registry completeness (50 codes, all have name_ru/name_en/family), `family_to_isu` round-trips, `ML_TYPE_TO_FAMILY` covers all TAS outputs. `test_metrics_registry` — jump_height matches `ALL_JUMPS`, not spins. `test_remap_to_isu` — `(axel, 3)→"3A"`, `(toe_loop, 1)→"1T"`, `(waltz_jump, _)→"1A"`, `(unknown, 3)→None`. `test_worker_isu_compose` — end-to-end TAS+phase→code. `test_migration` — sessions wiped, new session stores `"3A"`.
- **ML**: `test_phase_detector_rotations` — synthetic rotation trajectory → correct int. `test_isu_remap` — table-driven over TAS types × rotations.
- **Mobile**: `ElementLabelsTest` — `elementTypes` = ISU code list; `elementLabel("3A")` resolves. Reuses the #333 test seam.
- **E2E (Maestro)**: upload-pipeline flow stores an ISU code; session-detail shows `"3A — Triple Axel"` (en) / `"3A — Тройной Аксель"` (ru). The `tapOn: "axel"` selector from #333 updates to `tapOn: "3A"` (or the family picker).

## Scope Boundaries (explicit non-goals)

- **Spin level detection** (CSp1 vs CSp4): hard, needs a dedicated level classifier. This spec maps spins to base-level codes (`CSp1`, `StSq1`, `ChSq1`) and flags spin-level detection as a **follow-up issue**, not silently approximated.
- **TAS retraining**: out of scope (decision 4). Remap bridges the old classifier output.
- **Combo jump support** (`3A+3T`): `elements_db` has `combo_eligible` but session stores a single `element_type`. Combos are a separate data model — not in this spec.
- **Historical analytics**: wiping sessions (decision 3) means no historical trend continuity. Acceptable for dev-stage; revisit before prod launch.

## Migration Sequence (for the implementation plan)

1. Extend `elements_db.py` (registry fields + helpers) + tests.
2. `GET /metrics/elements` endpoint + schema.
3. `metrics_registry.py` → ISU code groups + update `MetricDef.element_types`.
4. `ml/src/analysis/isu_remap.py` + `phase_detector` rotation counting + tests.
5. `worker.py` remap wiring.
6. Alembic wipe migration.
7. Mobile: `elementTypes` → ISU codes + string resources + picker grouping.
8. Frontend: registry fetch + ISU-code labels.
9. E2E Maestro flow update (`tapOn: "3A"`).
10. Open follow-up issue: spin-level detection.

## Open Questions for the Implementing Agent

- **Mobile picker UX**: family-then-rotation, or full-code list? Spec leaves this to the plan; recommend family grouping (cleaner for users who know "I did an Axel" not "I did a triple Axel"). Validate with a quick Maestro flow.
- **Registry versioning**: how aggressively to cache in mobile/frontend? Suggest: cache + `If-None-Match`/version header, refresh on app cold-start. Detail in plan.
- **`waltz_jump` mapping**: waltz = 1.5 rotation axel = ISU `1A` (single axel is also 1.5). Confirm `waltz_jump → "1A"` alias is correct (it is, per ISU: waltz jump IS the single axel). Document in `ML_TYPE_TO_FAMILY`.