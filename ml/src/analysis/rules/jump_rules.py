"""Recommendation rules for jump elements.

These rules generate specific Russian recommendations for common jump errors.
"""

import math

from ...types import RecommendationRule


def _is_bad(value: float, ref_range: tuple[float, float]) -> bool:
    """Check if value is outside acceptable range.

    #887: NaN-aware — a non-finite value is "unknown", not "bad". The bare
    chained comparison `not (low <= nan <= high)` evaluates to True (NaN
    comparisons are False, so the chain is False, and `not False` is True),
    which would false-trigger a rule on missing data. NaN metrics must not
    produce actionable advice. The Recommender.recommend entry-guard (#584)
    skips non-finite values first; this guard is defense-in-depth for any
    direct caller of _is_bad.
    """
    if not math.isfinite(value):
        return False
    return not (ref_range[0] <= value <= ref_range[1])


# Common rules shared by all jumps — avoids duplication across element lists
_COMMON_JUMP_RULES = [
    RecommendationRule(
        metric_name="sensor_confidence",
        condition=_is_bad,
        priority=0,
        templates={
            "too_low": "Недостаточная уверенность сенсоров ({value:.2f}). Повтори элемент с обоими плотно закреплёнными датчиками.",
            "default": "Сенсорный сигнал пригоден для анализа.",
        },
    ),
    RecommendationRule(
        metric_name="rotation_symmetry",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": "Есть асимметрия вращения коньков ({value:.2f}). Проверь положение корпуса и опорной ноги.",
            "default": "Вращение коньков симметрично.",
        },
    ),
    RecommendationRule(
        metric_name="imu_peak_delta",
        condition=_is_bad,
        priority=1,
        templates={
            "too_high": "Пики вращения коньков расходятся на {value:.0f}мс. Проверь синхронность входа в прыжок.",
            "default": "Пики вращения коньков синхронны.",
        },
    ),
    RecommendationRule(
        metric_name="imu_offset_error",
        condition=_is_bad,
        priority=0,
        templates={
            "too_high": "Ошибка синхронизации IMU составляет {value:.0f}мс. Повтори запись после подключения обоих сенсоров.",
            "default": "Временная синхронизация IMU стабильна.",
        },
    ),
    RecommendationRule(
        metric_name="airtime",
        condition=_is_bad,
        priority=0,
        templates={
            "too_low": (
                "Недостаточное время полёта ({value:.2f}с вместо {target_min:.2f}-{target_max:.2f}с). "
                "Работай над отталкиванием: укрепляй икроножные мышцы (прыжки на скакалке, "
                "выпады, упражнения на степ-платформе)."
            ),
            "too_high": ("Отличное время полёта! Это выше референса, что хорошо для вращения."),
            "default": "Проверь технику отталкивания.",
        },
    ),
    RecommendationRule(
        metric_name="landing_knee_angle",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": (
                "Колени слишком прямые при приземлении (угол {value:.0f}° вместо {target_min:.0f}-{target_max:.0f}°). "
                "Старайся приземляться на более согнутые колени для амортизации. "
                "Это защитит колени и улучшит баланс."
            ),
            "too_high": (
                "Чрезмерное сгибание коленей при приземлении (угол {value:.0f}° вместо {target_min:.0f}-{target_max:.0f}°). "
                "Выпрями ноги в момент касания льда."
            ),
            "default": "Следи за сгибанием коленей при приземлении.",
        },
    ),
    RecommendationRule(
        metric_name="max_height",
        condition=_is_bad,
        priority=2,
        templates={
            "too_low": (
                "Недостаточная высота прыжка ({value:.2f} вместо {target_min:.2f}-{target_max:.2f}). "
                "Работай над силой отталкивания: приседания, прыжки на двух ногах, "
                "упражнения на взрывную силу."
            ),
            # #558: explicit too_high template. A high jump is usually OK
            # (not a defect), but if it crosses an upper bound the skater
            # may be over-rotating. Generic feedback acknowledges the high
            # direction so the user isn't told to "monitor" something
            # they did well.
            "too_high": (
                "Необычно высокий прыжок ({value:.2f} выше {target_max:.2f}). "
                "Проверь время полёта и стабильность — слишком высокий прыжок "
                "может указывать на избыточное отталкивание."
            ),
            "default": "Следи за высотой прыжка.",
        },
    ),
    RecommendationRule(
        metric_name="relative_jump_height",
        condition=_is_bad,
        priority=2,
        templates={
            "too_low": (
                "Недостаточная высота прыжка относительно длины тела ({value:.2f} вместо {target_min:.2f}-{target_max:.2f}). "
                "Работай над силой отталкивания: приседания, прыжки на двух ногах."
            ),
            # #558: too_high template.
            "too_high": (
                "Необычно высокий прыжок ({value:.2f} выше {target_max:.2f}). "
                "Проверь технику — избыточная высота может снижать контроль вращения."
            ),
            "default": "Следи за высотой прыжка.",
        },
    ),
    RecommendationRule(
        metric_name="rotation_speed",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": (
                "Недостаточная скорость вращения ({value:.0f}°/с вместо {target_min:.0f}-{target_max:.0f}°/с). "
                "Работай над группировкой в воздухе: руки ближе к телу, плотная группировка."
            ),
            "too_high": ("Отличная скорость вращения! Это выше референса."),
            "default": "Контролируй скорость вращения.",
        },
    ),
    RecommendationRule(
        metric_name="landing_com_velocity",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": (
                "Жёсткое приземление (скорость CoM {value:.2f} norm/s, целевой диапазон {target_min:.2f}-{target_max:.2f}). "
                "Приземляйся мягче, амортизируя сгибанием коленей. "
                "Резкое торможение = плоское лезвие или зубец."
            ),
            # #558: too_high means the skater barely decelerated — they're
            # probably landing on a back-edge or gliding, which is also
            # a stability issue (no real edge control).
            "too_high": (
                "Недостаточное торможение при приземлении (скорость CoM {value:.2f} выше {target_max:.2f}). "
                "Возможно, приземление на заднее ребро — работай над контролем выезда."
            ),
            "default": "Контролируй приземление.",
        },
    ),
    RecommendationRule(
        metric_name="landing_smoothness",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": (
                "Нестабильное приземление (smoothness {value:.2f}, целевой {target_min:.2f}-{target_max:.2f}). "
                "Работай над балансом после выезда: удерживай центр тяжести над опорной ногой."
            ),
            # #558: too_high smoothness is unusual (smoothness is bounded
            # 0-1). Acknowledge so the user knows the metric is detected
            # as above the reference range, not "needs monitoring".
            "too_high": (
                "Аномально гладкое приземление ({value:.2f} выше {target_max:.2f}). "
                "Проверь, не завышена ли метрика из-за плоской фазы — сравни с реальной видеозаписью."
            ),
            "default": "Улучшай стабильность после приземления.",
        },
    ),
    RecommendationRule(
        metric_name="approach_torso_lean",
        condition=_is_bad,
        priority=2,
        templates={
            "too_low": (
                "Слишком сильный наклон назад при заходе ({value:.1f}°). "
                "Для этого прыжка держи торс более вертикально."
            ),
            "too_high": (
                "Слишком сильный наклон вперёд при заходе ({value:.1f}°). Проверь технику захода."
            ),
            "default": "Контролируй наклон торса при заходе.",
        },
    ),
    RecommendationRule(
        metric_name="toe_assist_proxy",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": (
                "Приземление слишком резкое — возможно, приземляешься на зубец конька. "
                "Старайся касаться льда плавно, через ребро лезвия."
            ),
            # #558: too_high = skater over-assisted with toe pick.
            "too_high": (
                "Слишком сильная помощь зубцом ({value:.2f} выше {target_max:.2f}). "
                "Приземление на плоское лезвие снижает GOE — работай над плавным перекатом."
            ),
            "default": "Контролируй качество приземления.",
        },
    ),
    RecommendationRule(
        metric_name="hard_landing",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": (
                "Жесткое приземление. Работай над амортизацией: сгибай колени и бедра, приземляйся мягко."
            ),
            # #558: hard_landing scale is 0.0=very hard, 1.0=soft. A
            # "too_high" value is GOOD — soft landing, perfect
            # amortization. Acknowledge so the user gets positive
            # feedback (currently they get a generic "improve softness"
            # message that suggests something is wrong).
            "too_high": "Отличное мягкое приземление! Амортизация идеальная.",
            "default": "Контролируй мягкость приземления.",
        },
    ),
    RecommendationRule(
        metric_name="goe_score",
        condition=_is_bad,
        priority=3,
        templates={
            "too_low": (
                "Оценка качества элемента: {value:.1f}/10 (ниже {target_min:.1f}). "
                "Работай над: высотой, группировкой, приземлением, торсом."
            ),
            # #558: too_high GOE score is GOOD (above max). Acknowledge.
            "too_high": (
                "Превосходное качество элемента: {value:.1f}/10 (выше {target_max:.1f}). "
                "Отличная работа, продолжай в том же духе!"
            ),
            "default": "Улучшай общее качество элемента.",
        },
    ),
]


# Waltz jump rules
WALTZ_JUMP_RULES = [
    RecommendationRule(
        metric_name="arm_position_score",
        condition=_is_bad,
        priority=0,
        templates={
            "too_low": (
                "Руки 'разлетаются' во время прыжка (score {value:.2f}). "
                "Выпрями руки вперёд и делай тройки с зафиксированными руками. "
                "Руки служат балансиром — если они болтаются, теряется ось вращения."
            ),
            "too_high": ("Отличная позиция рук! Они хорошо зафиксированы."),
            "default": "Контролируй позицию рук.",
        },
    ),
    *_COMMON_JUMP_RULES,
]


# Toe loop rules
TOE_LOOP_RULES = [
    RecommendationRule(
        metric_name="toe_pick_timing",
        condition=_is_bad,
        priority=0,
        templates={
            "too_low": (
                "Слишком долгая подготовка к удару зубцом. Укороти время между заходом и отталкиванием."
            ),
            "too_high": ("Слишком резкий удар зубцом. Постепенно наращивай силу толчка."),
            "default": "Работай над таймингом зубцового удара.",
        },
    ),
    *_COMMON_JUMP_RULES,
]


# Flip rules
FLIP_RULES = [
    RecommendationRule(
        metric_name="pick_quality",
        condition=_is_bad,
        priority=0,
        templates={
            "too_low": ("Нечёткий удар зубцом при заходе на флип. Следи за точностью удара."),
            "default": "Контролируй точность зубцового удара.",
        },
    ),
    RecommendationRule(
        metric_name="air_position",
        condition=_is_bad,
        priority=1,
        templates={
            "too_low": (
                "Расслабленная позиция в воздухе (score {value:.2f}). "
                "Группируй плотнее: руки прижаты к телу, ноги вместе."
            ),
            "default": "Работай над группировкой в воздухе.",
        },
    ),
    *_COMMON_JUMP_RULES,
]


# Salchow rules
SALCHOW_RULES = [*_COMMON_JUMP_RULES]


# Loop rules
LOOP_RULES = [*_COMMON_JUMP_RULES]


# Lutz rules
LUTZ_RULES = [*_COMMON_JUMP_RULES]


# Axel rules
AXEL_RULES = [*_COMMON_JUMP_RULES]
