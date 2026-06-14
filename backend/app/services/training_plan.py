"""Training plan generation from weakest subscores."""

from app.schemas import SubScoreSchema, TrainingPlanItemSchema

EXERCISE_RECOMMENDATIONS = {
    "takeoff_power": [
        {"label_ru": "Прыжки через скакалку", "description_ru": "3x30 сек быстрых прыжков"},
        {"label_ru": "Приседания с выпрыгиванием", "description_ru": "3x10 прыжков из глубокого приседа"},
    ],
    "rotation_axis": [
        {"label_ru": "Вращение на месте", "description_ru": "Контроль плеч — 2 минуты"},
        {"label_ru": "Спирали на одной ноге", "description_ru": "3x30 сек с фиксацией оси"},
    ],
    "arm_coordination": [
        {"label_ru": "Растяжка плечевого пояса", "description_ru": "Комплекс на раскрытие рук — 5 минут"},
        {"label_ru": "Хореография рук", "description_ru": "Плавные переходы — 3 минуты"},
    ],
    "landing_absorption": [
        {"label_ru": "Упражнение на амортизацию", "description_ru": "3x5 приземлений с фокусом на угол колена ≥ 110°"},
        {"label_ru": "Прыжки на мягкой поверхности", "description_ru": "5x3 прыжка с мягким приземлением"},
    ],
    "core_stability": [
        {"label_ru": "Планка с вращением", "description_ru": "3x30 сек боковая планка"},
        {"label_ru": "Упражнения на баланс", "description_ru": "Стойка на одной ноге — 3x30 сек"},
    ],
}


def generate_training_plan(subscores: list[SubScoreSchema], session_id: str | None = None) -> list[TrainingPlanItemSchema]:
    """Generate training plan prioritized by weakest subscores."""
    sorted_scores = sorted(subscores, key=lambda s: s.value)
    items = []
    for i, score in enumerate(sorted_scores[:4], 1):
        recs = EXERCISE_RECOMMENDATIONS.get(score.name, [])
        if recs:
            rec = recs[0]  # Pick first recommendation
            items.append(
                TrainingPlanItemSchema(
                    id=str(i),
                    priority=i,
                    label_ru=rec["label_ru"],
                    description_ru=rec["description_ru"],
                    completed=False,
                )
            )
    return items