"""ISU GOE grader — map biomechanical metrics to ISU GOE grade (-5 to +5).

Implements ISU Communication 2701 positive bullets and error reductions.
Score formula: BV * (1 + grade * 0.10).
"""

from __future__ import annotations

from ..types import GOEGrade, MetricResult

# Positive bullet thresholds
_THRESHOLDS = {
    "good_height": 0.20,
    "good_landing_velocity_min": -1.5,
    "good_landing_velocity_max": 0.0,
    "good_landing_smoothness": 0.7,
    "good_landing_hard_max": 0.3,
    "good_rotation_speed_min": 300,
    "good_airtime_min": 0.3,
    "creative_approach_direction_change": 40,
    "good_arm_position_score": 0.7,
    "good_trunk_recovery": 0.6,
    # Negative thresholds
    "fall_smoothness_max": 0.05,
    "fall_hard_landing_max": 0.1,
    "poor_airtime_max": 0.2,
    "wrong_edge_direction_change": 90,
    "unclear_edge_direction_change": 60,
    "two_foot_toe_assist_max": 0.3,
    "touch_down_stability_max": 0.3,
}

# All metric names used by criteria
_CRITERIA_METRICS = {
    "max_height",
    "landing_com_velocity",
    "landing_smoothness",
    "hard_landing",
    "rotation_speed",
    "airtime",
    "approach_direction_change",
    "arm_position_score",
    "landing_trunk_recovery",
    "rotation_count",
    "landing_knee_stability",
    "toe_assist_proxy",
}

_MANDATORY_BULLETS = {"height_length", "takeoff_landing", "effortless"}


class GOEGrader:
    """Map biomechanical metrics to ISU GOE grade."""

    def compute_goe_grade(
        self,
        metrics: list[MetricResult],
        base_value: float,
        expected_rotations: float,
    ) -> GOEGrade:
        mv = {m.name: m.value for m in metrics}
        modifier = self.detect_modifier(mv, expected_rotations)
        bv = self._adjusted_base_value(base_value, modifier)
        positives = self.count_positives(mv)
        negatives = self.detect_negatives(mv)

        if self._is_fall(mv):
            grade = -5
        else:
            grade = len(positives)
            has_error = bool(negatives) or modifier != ""
            if has_error and grade > 3:
                grade = 3
            neg_weight = self._negative_weight(negatives, mv)
            grade -= neg_weight
            bullets_1_3_met = _MANDATORY_BULLETS.issubset(set(positives))
            if grade >= 4 and not bullets_1_3_met:
                grade = 3
            grade = max(-5, min(5, grade))

        estimated_score = bv * (1 + grade * 0.10)
        confidence = self._compute_confidence(mv)

        return GOEGrade(
            grade=grade,
            base_value=round(bv, 2),
            estimated_score=round(estimated_score, 2),
            modifier=modifier,
            positives=positives,
            negatives=negatives,
            confidence=round(confidence, 2),
        )

    def detect_modifier(
        self,
        metrics: dict[str, float] | list[MetricResult],
        expected_rotations: float,
    ) -> str:
        mv = metrics if isinstance(metrics, dict) else {m.name: m.value for m in metrics}
        actual = mv.get("rotation_count", expected_rotations)
        shortfall = expected_rotations - actual

        if shortfall >= 0.5:
            return "<<"
        if shortfall > 0.25:
            return "<"
        if 0 < shortfall <= 0.25:
            return "q"

        direction_change = abs(mv.get("approach_direction_change", 0))
        if direction_change > _THRESHOLDS["wrong_edge_direction_change"]:
            return "e"
        if direction_change > _THRESHOLDS["unclear_edge_direction_change"]:
            return "!"
        return ""

    def count_positives(
        self,
        metrics: dict[str, float] | list[MetricResult],
    ) -> list[str]:
        mv = metrics if isinstance(metrics, dict) else {m.name: m.value for m in metrics}
        positives: list[str] = []

        # Bullet 1: Very good height AND very good length
        height_ok = mv.get("max_height", 0) >= _THRESHOLDS["good_height"]
        velocity_ok = (
            _THRESHOLDS["good_landing_velocity_min"]
            <= mv.get("landing_com_velocity", -999)
            <= _THRESHOLDS["good_landing_velocity_max"]
        )
        if height_ok and velocity_ok:
            positives.append("height_length")

        # Bullet 2: Good take-off and landing
        smooth_ok = mv.get("landing_smoothness", 0) >= _THRESHOLDS["good_landing_smoothness"]
        hard_ok = mv.get("hard_landing", 1) < _THRESHOLDS["good_landing_hard_max"]
        if smooth_ok and hard_ok:
            positives.append("takeoff_landing")

        # Bullet 3: Effortless throughout
        speed_ok = mv.get("rotation_speed", 0) >= _THRESHOLDS["good_rotation_speed_min"]
        airtime_ok = mv.get("airtime", 0) >= _THRESHOLDS["good_airtime_min"]
        if speed_ok and airtime_ok:
            positives.append("effortless")

        # Bullet 4: Steps before jump / creative entry
        if (
            abs(mv.get("approach_direction_change", 0))
            >= _THRESHOLDS["creative_approach_direction_change"]
        ):
            positives.append("steps_creative_entry")

        # Bullet 5: Very good body position
        arm_ok = mv.get("arm_position_score", 0) >= _THRESHOLDS["good_arm_position_score"]
        trunk_ok = mv.get("landing_trunk_recovery", 0) >= _THRESHOLDS["good_trunk_recovery"]
        if arm_ok and trunk_ok:
            positives.append("body_position")

        # Bullet 6: Matches music — not detectable
        return positives

    def detect_negatives(
        self,
        metrics: dict[str, float] | list[MetricResult],
    ) -> list[str]:
        mv = metrics if isinstance(metrics, dict) else {m.name: m.value for m in metrics}
        negatives: list[str] = []

        if self._is_fall(mv):
            negatives.append("fall")
        if mv.get("airtime", 999) < _THRESHOLDS["poor_airtime_max"]:
            negatives.append("poor_speed_height")
        if mv.get("toe_assist_proxy", 999) < _THRESHOLDS["two_foot_toe_assist_max"]:
            negatives.append("two_foot_landing")
        if mv.get("landing_knee_stability", 999) < _THRESHOLDS["touch_down_stability_max"]:
            negatives.append("touch_down")
        return negatives

    def _is_fall(self, mv: dict[str, float]) -> bool:
        # compute_hard_landing scale: 1.0 = soft landing, 0.0 = very hard impact
        # (metrics.py:990). A fall is a HARD impact (low hard_landing) + unstable
        # landing (low smoothness), not a soft landing. See #421.
        return (
            mv.get("landing_smoothness", 1) < _THRESHOLDS["fall_smoothness_max"]
            and mv.get("hard_landing", 1) < _THRESHOLDS["fall_hard_landing_max"]
        )

    def _adjusted_base_value(self, clean_bv: float, modifier: str) -> float:
        match modifier:
            case "":
                return clean_bv
            case "q":
                return clean_bv
            case "<":
                return clean_bv * 0.80
            case "<<" | "e" | "!":
                return clean_bv  # Downgraded/e/! need external BV lookup
            case _:
                return clean_bv

    def _negative_weight(self, negatives: list[str], mv: dict[str, float]) -> int:
        weight = 0
        for neg in negatives:
            if neg == "fall":
                weight += 5
            elif neg == "two_foot_landing":
                weight += 3
            elif neg == "touch_down":
                stability = mv.get("landing_knee_stability", 1)
                weight += 1 if stability > 0.15 else 2
            elif neg == "poor_speed_height":
                weight += 1
        return weight

    def _compute_confidence(self, mv: dict[str, float]) -> float:
        available = sum(1 for m in _CRITERIA_METRICS if m in mv)
        return available / len(_CRITERIA_METRICS)
