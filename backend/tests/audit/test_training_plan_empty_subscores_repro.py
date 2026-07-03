"""RED repro — training_plan route: IndexError when subscores empty after sort.

Bug: routes/training_plans.py:42 does `items[0].label_ru if items else None`
which correctly guards against empty items. BUT the CRUDE create_plan()
doesn't guard against training plans with empty items — items=[] is stored
as JSON []. When the frontend fetches TrainingPlanResponse, items=[] is
valid but useless. The real bug is that generate_training_plan filters by
EXERCISE_RECOMMENDATIONS dict — metrics with no entry (like "symmetry",
"estimated_score") produce 0 recommendations, so a user with only those
subscoress gets an empty training plan stored in the DB.

Actually: re-checking — generate_training_plan sorts by score value and
takes top 4, then only adds items for subscores whose .name exists in
EXERCISE_RECOMMENDATIONS. Unknown metrics are skipped. This IS safe for
empty input. The route also guards `items[0]`. NOT a crash bug.

However: there IS a subtle bug — generate_training_plan uses EXERCISE_RECOMMENDATIONS
as the ONLY source of exercises. The dict has 5 keys (takeoff_power,
rotation_axis, arm_coordination, landing_absorption, core_stability) but
the multi-score SubScore schema has EXACTLY those 5 names. So it works by
coincidence. If a new SubScore name is added to the ML output without
updating EXERCISE_RECOMMENDATIONS, it gets silently dropped from the plan.
"""

# This file documents a latent issue, not a crash. Kept as a guard.
import pytest


def test_generate_training_plan_empty_subscores_returns_empty():
    """generate_training_plan([]) returns [] — no crash."""
    from app.services.training_plan import generate_training_plan

    result = generate_training_plan([])
    assert result == [], f"Expected empty list for empty subscores, got {result}"


def test_generate_training_plan_unknown_subscore_returns_empty():
    """Subscore with name not in EXERCISE_RECOMMENDATIONS yields empty items.

    #550 fix: validate subscore.name against EXERCISE_RECOMMENDATIONS. A
    typo / new subscore name (e.g. "symmetry") used to silently return
    an empty training plan — indistinguishable from "no exercises
    needed". The user thinks the training plan is complete when in
    fact the new subscore was dropped. Raise ValueError with a clear
    message listing the registered categories.
    """

    from app.schemas import SubScoreSchema
    from app.services.training_plan import generate_training_plan

    # "symmetry" has no EXERCISE_RECOMMENDATIONS entry — must raise.
    score = SubScoreSchema(
        name="symmetry",
        label_ru="Симметрия",
        value=0.3,
        confidence=0.5,
        contributing_metrics=["symmetry"],
    )
    with pytest.raises(ValueError, match="Unknown subscore"):
        generate_training_plan([score])


def test_route_focus_subscore_guard():
    """Route handler correctly guards items[0] with 'if items else None'."""
    import inspect
    from pathlib import Path

    from app.routes.training_plans import TrainingPlansController

    # Can't getsource on Litestar Controller method — verify via file read
    source_file = inspect.getfile(TrainingPlansController)
    with Path(source_file).open() as f:
        source = f.read()
    # The guard exists in the route: items[0].label_ru if items else None
    assert "if items else" in source, "Missing guard for empty items in training_plans route"
