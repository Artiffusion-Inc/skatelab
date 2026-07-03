"""Training plan generation from weakest subscores."""

from app.schemas import SubScoreSchema, TrainingPlanItemSchema

EXERCISE_RECOMMENDATIONS = {
    "takeoff_power": [
        {
            "label_ru": "Прыжки через скакалку",
            "description_ru": "3x30 сек быстрых прыжков",
            "label_en": "Jump rope",
            "description_en": "3x30 sec fast jumps",
        },
        {
            "label_ru": "Приседания с выпрыгиванием",
            "description_ru": "3x10 прыжков из глубокого приседа",
            "label_en": "Squat jumps",
            "description_en": "3x10 jumps from deep squat",
        },
    ],
    "rotation_axis": [
        {
            "label_ru": "Вращение на месте",
            "description_ru": "Контроль плеч — 2 минуты",
            "label_en": "Spot rotation",
            "description_en": "Shoulder control — 2 minutes",
        },
        {
            "label_ru": "Спирали на одной ноге",
            "description_ru": "3x30 сек с фиксацией оси",
            "label_en": "One-leg spirals",
            "description_en": "3x30 sec with axis hold",
        },
    ],
    "arm_coordination": [
        {
            "label_ru": "Растяжка плечевого пояса",
            "description_ru": "Комплекс на раскрытие рук — 5 минут",
            "label_en": "Shoulder stretch",
            "description_en": "Arm opening complex — 5 min",
        },
        {
            "label_ru": "Хореография рук",
            "description_ru": "Плавные переходы — 3 минуты",
            "label_en": "Arm choreography",
            "description_en": "Smooth transitions — 3 min",
        },
    ],
    "landing_absorption": [
        {
            "label_ru": "Упражнение на амортизацию",
            "description_ru": "3x5 приземлений с фокусом на угол колена ≥ 110°",
            "label_en": "Absorption exercise",
            "description_en": "3x5 landings focusing knee angle ≥ 110°",
        },
        {
            "label_ru": "Прыжки на мягкой поверхности",
            "description_ru": "5x3 прыжка с мягким приземлением",
            "label_en": "Soft-surface jumps",
            "description_en": "5x3 jumps with soft landing",
        },
    ],
    "core_stability": [
        {
            "label_ru": "Планка с вращением",
            "description_ru": "3x30 сек боковая планка",
            "label_en": "Plank with rotation",
            "description_en": "3x30 sec side plank",
        },
        {
            "label_ru": "Упражнения на баланс",
            "description_ru": "Стойка на одной ноге — 3x30 сек",
            "label_en": "Balance exercises",
            "description_en": "Single-leg stand — 3x30 sec",
        },
    ],
}


def generate_training_plan(
    subscores: list[SubScoreSchema], session_id: str | None = None, lang: str = "ru"
) -> list[TrainingPlanItemSchema]:
    """Generate training plan prioritized by weakest subscores.

    Args:
        subscores: List of 5 subscores from multi-dimensional scoring.
        session_id: Optional session ID for reference.
        lang: Output language — "ru" (default, backward compatible) or "en".
            The selected language text is placed into the ``label_ru`` /
            ``description_ru`` fields of each :class:`TrainingPlanItemSchema`
            (the field names are kept for API-contract stability; the caller
            chooses the language of the content).
    """
    label_key = "label_en" if lang == "en" else "label_ru"
    desc_key = "description_en" if lang == "en" else "description_ru"
    sorted_scores = sorted(subscores, key=lambda s: s.value)
    items = []
    for i, score in enumerate(sorted_scores[:4], 1):
        # #550: validate subscore.name against EXERCISE_RECOMMENDATIONS. A
        # typo / new subscore name used to silently return an empty
        # training plan (no items for that subscore) — indistinguishable
        # from "no exercises needed". The user thinks the plan is
        # complete when the new subscore was dropped. Raise ValueError
        # with a clear message listing the registered categories.
        if score.name not in EXERCISE_RECOMMENDATIONS:
            raise ValueError(
                f"Unknown subscore: {score.name!r}. "
                f"Registered: {sorted(EXERCISE_RECOMMENDATIONS.keys())}"
            )
        recs = EXERCISE_RECOMMENDATIONS[score.name]
        if recs:
            rec = recs[0]  # Pick first recommendation
            items.append(
                TrainingPlanItemSchema(
                    id=str(i),
                    priority=i,
                    label_ru=rec[label_key],
                    description_ru=rec[desc_key],
                    completed=False,
                )
            )
    return items
