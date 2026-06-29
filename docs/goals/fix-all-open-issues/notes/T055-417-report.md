# T055 report — Fix #417 (lang plumbing HTTP→worker→GPU→recommender + training plan)

Status: **DONE_WITH_CONCERNS** (one justified scope expansion — see below).

## Summary

Plumbed `user.language` from the HTTP request through the worker → Vast.ai →
GPU server → recommender, and to the training-plan route. en-US users now get
English GOE summaries and English training-plan items instead of Russian.

## Commits (on branch `worktree-fix-417-lang-plumbing`)

1. `31034c61` — `test(backend): RED lang plumbing enqueue test (#417)`
2. `294ad4b2` — `fix(backend): plumb user.language to process_video_task enqueue (#417)`
3. `04a4a241` — `test(backend): RED training-plan lang forwarding test (#417)`
4. `a0f6dc28` — `fix(backend): plumb user.language to training-plan generation (#417)`
5. `cdcf0741` — `fix(ml): plumb lang to pipeline + gpu_server recommender (#417)`

## Sites changed

### 1. `backend/app/routes/process.py` (enqueue `lang`)
Added `lang=user.language,` to the `enqueue_job("process_video_task", ...)` kwargs,
after `user_id=str(user.id)`, before `_queue_name=`:

```python
            session_id=data.session_id,
            user_id=str(user.id),
            lang=user.language,
            _queue_name="skatelab:queue:heavy",
```

### 2. `backend/app/worker.py` (`process_video_task` accept + forward `lang`)
Signature (after `user_id: str | None = None,`):
```python
    session_id: str | None = None,
    user_id: str | None = None,
    lang: str = "ru",
) -> dict[str, Any]:
```
`process_video_remote_async(...)` call — added `lang=lang,`:
```python
                element_type=element_type,
                isu_code=isu_code,
                lang=lang,
            )
```

### 3. `backend/app/vastai/client.py` (`process_video_remote_async` accept + payload `lang`)
Signature (after `isu_code: str | None = None,`):
```python
    element_type: str | None = None,
    isu_code: str | None = None,
    lang: str = "ru",
) -> VastResult:
```
`payload` dict — added `"lang": lang,` after `"isu_code": isu_code,`:
```python
        "element_type": element_type,
        "isu_code": isu_code,
        "lang": lang,
        "s3_endpoint_url": settings.s3.endpoint_url,
```

### 4. `ml/gpu_server/server.py` (`ProcessRequest.lang` + pass to recommender)
`ProcessRequest` (after `isu_code: str | None = None,`):
```python
    element_type: str | None = None
    isu_code: str | None = None
    lang: str = "ru"
```
Recommender call:
```python
                        recommender = Recommender()
                        recommendations = recommender.recommend_with_goe(
                            metrics, req.element_type, goe_grade, lang=req.lang
                        )
```

### 5. `ml/src/pipeline.py` (`analyze` + `analyze_async` accept `lang`, forward to recommender)
`analyze` signature — added `lang: str = "ru",` after `isu_code: str | None = None,`
(+ docstring). `recommend_with_goe` call:
```python
            recommendations = recommender.recommend_with_goe(
                metrics, element_type, goe_grade, lang=lang
            )
```
`analyze_async` signature — added `lang: str = "ru",`. The `recommend()` call in
`analyze_async` was left as-is (no `lang` param) with a code comment:
```python
            recommender = self._get_recommender()
            # recommend() rule templates are Russian-only (rules/*.py); lang
            # plumbing is for the GOE summary + training_plan only (#417).
            recommendations = recommender.recommend(metrics, element_type)
```
`analyze` has NO bare `recommend()` fallback call (only `recommend_with_goe` at
line 388); `analyze_async` has only the bare `recommend()` call (no goe path).
Both confirmed via `grep -n 'recommender\|recommend' ml/src/pipeline.py`.

### 6. `backend/app/routes/training_plans.py` + `backend/app/services/training_plan.py` (pass `lang=user.language`)

**Scope expansion (justified):** The brief's site 6 assumed the route calls the
ML `ml/src/analysis/training_plan.generate_training_plan` (which #415 gave a
`lang` param). It does NOT — the route imports
`from app.services.training_plan import generate_training_plan`, a **separate
backend-service duplicate** that is Russian-only (no `lang` param, no
`label_en`/`description_en`). Passing `lang=` to it caused a `TypeError` (500).

To actually achieve #417's stated intent ("en-US users get English training
plans") I added a `lang` param + English labels to
`backend/app/services/training_plan.py` (mirroring the ML module's
`EXERCISE_RECOMMENDATIONS`), and the route passes `lang=user.language`:

Route (`training_plans.py:35`):
```python
        items = generate_training_plan(
            subscores, session_id=data.session_id, lang=user.language
        )
```

Service (`app/services/training_plan.py`): added `label_en`/`description_en` to
each `EXERCISE_RECOMMENDATIONS` entry (matching the ML module verbatim) and:
```python
def generate_training_plan(
    subscores: list[SubScoreSchema], session_id: str | None = None, lang: str = "ru"
) -> list[TrainingPlanItemSchema]:
    label_key = "label_en" if lang == "en" else "label_ru"
    desc_key = "description_en" if lang == "en" else "description_ru"
    ...
```

This is a 7th source file (the brief listed 6). It is the actual callee of site
6, so it is necessary — without it the route's `lang=user.language` would crash
and the English training-plan path stays dead. Architectural constraint
"backend routes no ML imports" forbids switching the route to the ML function,
so the backend service is the correct place. `lang` default `"ru"` keeps it
backward compatible.

## Tests (TDD)

### `backend/tests/routes/test_process_lang_plumbing.py` (NEW)
Mirrors `test_process_enqueue_session_idor_repro.py`: mocks
`create_task_state` + `arq_pool.enqueue_job`, creates a user with
`language="en"` and one with `language="ru"`, calls `POST /v1/process/queue`,
asserts `enqueue_job` kwargs contain `lang="en"` (en user) and `lang="ru"`
(default user). RED before sites 1+2 (`lang=None` in kwargs), GREEN after.

### `backend/tests/test_training_plan_lang.py` (NEW)
Creates an `language="en"` user + session + SessionScore (weakest subscore =
`takeoff_power`), calls `POST /v1/training-plans/generate`, asserts the first
returned item `label_ru` field holds English content ("Jump rope" / "Squat
jumps", not "Прыжки через скакалку"). RED before site 6
(`label_ru='Прыжки через скакалку'`), GREEN after.

### ML pipeline test — SKIPPED (per brief)
`pipeline.analyze(..., lang="en")` needs a real video + GPU + ONNX models to
reach the `recommend_with_goe` call; unit-testing it without video is
impractical and stubbing a fake video just to test plumbing is forbidden by the
brief. Instead the plumbing endpoint is verified by:
- grep: `recommend_with_goe(..., lang=lang)` in `ml/src/pipeline.py:394`
- grep: `recommend_with_goe(..., lang=req.lang)` in `ml/gpu_server/server.py:522`
- `ml/tests/analysis/` + `ml/tests/test_pipeline.py` green (no regression; `lang`
  is additive with default `"ru"`).

The recommender English branch itself was already tested by #415.

## Verification commands + output

### Grep checks (all pass)
```
=== 1. process.py ===
79:            lang=user.language,
=== 2. worker.py ===
291:    lang: str = "ru",
368:                lang=lang,
=== 3. vastai/client.py ===
133:    lang: str = "ru",
163:        "lang": lang,
=== 4. gpu_server/server.py ===
207:    lang: str = "ru"
522:                            metrics, req.element_type, goe_grade, lang=req.lang
=== 5. pipeline.py ===
191:        lang: str = "ru",
394:                metrics, element_type, goe_grade, lang=lang
690:        lang: str = "ru",
858:            # recommend() rule templates are Russian-only (rules/*.py); lang
=== 6. training_plans.py ===
35:        items = generate_training_plan(subscores, session_id=data.session_id, lang=user.language)
=== services/training_plan.py ===
80:    ... lang: str = "ru"
93:    label_key = "label_en" if lang == "en" else "label_ru"
94:    desc_key = "description_en" if lang == "en" else "description_ru"
```

### Backend tests
- New tests: `uv run pytest backend/tests/routes/test_process_lang_plumbing.py
  backend/tests/test_training_plan_lang.py -q --no-cov` → **3 passed**.
- Routes + vastai subset: `uv run pytest backend/tests/routes/
  backend/tests/test_vastai_client.py
  backend/tests/test_vastai_client_extended.py -q --no-cov` → **174 passed**.
- Full backend suite (fast subset, `-m "not slow and not integration and not gpu"`):
  `uv run pytest backend/tests/ -q --no-cov -m "..." -x --timeout=60` →
  **616 passed, 11 skipped, 0 failed** (197s).

### ML tests
- Pipeline + analysis: `cd ml && uv run pytest tests/test_pipeline.py
  tests/test_pipeline_parallel.py tests/analysis/ -q --no-cov --timeout=60` →
  **395 passed, 12 deselected**.
- Full ml suite (non-gpu): `cd ml && uv run pytest tests/ -q --no-cov -m "not gpu"
  --timeout=60` → **1331 passed, 32 skipped, 4 failed**.

  The 4 failures are **pre-existing and unrelated** to this change:
  - `tests/detection/test_person_detector.py` (3) — needs the RF-DETR ONNX
    model file on disk (lazy-load + inference).
  - `tests/tas/test_dataset.py::test_mcfs_dataset_exists` — needs
    `data/datasets/mcfs` data files (asserts dataset row count > 0).

  None touch `pipeline.py` / `recommender` / `gpu_server` / `lang`. The
  pipeline + analysis suites (which cover the changed files) are fully green.

## Concerns

1. **Scope expansion (7th source file).** `backend/app/services/training_plan.py`
   was edited in addition to the 6 brief-listed files. Justified: the route's
   `generate_training_plan` callee is this backend service (Russian-only
   duplicate), NOT the ML function the brief assumed. Without adding `lang` +
   English labels here, the route's `lang=user.language` call crashes and #417's
   training-plan intent is unmet. The "no ML imports in routes" constraint
   forbids switching to the ML function, so the backend service is the correct
   place. `lang` default `"ru"` = backward compatible.

2. **Two parallel `generate_training_plan` implementations now drift-prone.**
   `ml/src/analysis/training_plan.py` and `backend/app/services/training_plan.py`
   both carry the same `EXERCISE_RECOMMENDATIONS` (ru + en). Future exercise
   edits must touch both. A follow-up could consolidate (e.g. backend service
   delegates to ML), but that violates the "no ML imports in backend routes"
   constraint, so it is left as-is for #417.

3. **ML pipeline `lang` forwarding is grep-verified, not unit-tested** (per brief
   site 5 decision — `pipeline.analyze` needs video/GPU). The recommender
   English branch was already covered by #415.

4. **`recommend()` (rule templates) stays Russian-only.** Per brief: rules/*.py
   translation is out of scope (#407 follow-up). Only the GOE summary +
   training-plan items are localized by #417.