"""Rule-based recommendation engine for skating technique.

This module generates specific, actionable recommendations in Russian
based on biomechanics metrics analysis.
"""

from ..types import GOEGrade, MetricResult, RecommendationRule
from .rules import jump_rules, three_turn_rules


class Recommender:
    """Generate recommendations based on biomechanics metrics.

    Uses a rule-based system where each metric that falls outside
    the ideal range triggers specific recommendations.
    """

    def __init__(self) -> None:
        """Initialize recommender with rule set."""
        self._rules: dict[str, list[RecommendationRule]] = {}
        self._build_rules()

    def recommend(
        self,
        metrics: list[MetricResult],
        element_type: str,
    ) -> list[str]:
        """Generate recommendations based on metrics.

        Args:
            metrics: List of computed MetricResult.
            element_type: Type of skating element.

        Returns:
            List of recommendation strings in Russian, sorted by priority.
        """
        recommendations: list[tuple[int, str]] = []

        # #559: validate element_type against registered rules. A typo
        # in element_type (e.g. "waltz" instead of "waltz_jump") used
        # to silently return [] — indistinguishable from "no problems
        # detected". The end user would see an empty recommendations
        # list and assume the element was perfect. Raise ValueError
        # with a clear message listing the registered types.
        if element_type not in self._rules:
            raise ValueError(
                f"Unknown element_type: {element_type!r}. Registered: {sorted(self._rules.keys())}"
            )

        # Get rules for element type
        element_rules = self._rules[element_type]

        # Check each metric against rules
        for metric in metrics:
            for rule in element_rules:
                if rule.metric_name != metric.name:
                    continue

                # Check if metric triggers rule
                if rule.condition(metric.value, metric.reference_range):
                    # Generate recommendation
                    severity = self._determine_severity(metric.value, metric.reference_range)
                    template = rule.templates.get(severity, rule.templates.get("default", ""))

                    # Format template with values
                    recommendation = template.format(
                        value=metric.value,
                        unit=metric.unit,
                        target_min=metric.reference_range[0],
                        target_max=metric.reference_range[1],
                    )

                    # Store with priority
                    recommendations.append((rule.priority, recommendation))

        # Sort by priority (lower = more critical) and return strings
        recommendations.sort(key=lambda x: x[0])
        return [rec for _, rec in recommendations]

    def recommend_with_goe(
        self,
        metrics: list[MetricResult],
        element_type: str,
        goe_grade: GOEGrade | None = None,
        lang: str = "ru",
    ) -> list[str]:
        """Generate recommendations with optional ISU GOE context.

        Args:
            metrics: List of computed MetricResult.
            element_type: Type of skating element.
            goe_grade: Optional GOEGrade from ISU GOE scoring.
            lang: Output language — "ru" (default, backward compatible)
                or "en" for English GOE summary.

        Returns:
            List of recommendation strings (Russian by default), with GOE
            summary prepended if goe_grade is provided.
        """
        recommendations = self.recommend(metrics, element_type)
        if goe_grade is None:
            return recommendations
        # Insert GOE summary as first recommendation
        goe_summary = self._format_goe_summary(goe_grade, lang)
        return [goe_summary, *recommendations]

    @staticmethod
    def _format_goe_summary(goe_grade: GOEGrade, lang: str) -> str:
        """Format a GOE summary line in the requested language.

        Args:
            goe_grade: GOEGrade from ISU GOE scoring.
            lang: "ru" or "en".

        Returns:
            Formatted GOE summary string.
        """
        if lang == "en":
            goe_summary = (
                f"GOE {goe_grade.grade:+d} "
                f"({len(goe_grade.positives)} positives, "
                f"{len(goe_grade.negatives)} negatives). "
                f"Element score: {goe_grade.estimated_score:.2f} points "
                f"(BV {goe_grade.base_value:.2f}"
            )
            if goe_grade.modifier:
                goe_summary += f", modifier {goe_grade.modifier}"
            goe_summary += f"). Confidence: {goe_grade.confidence:.0%}."
            return goe_summary
        # Default: Russian (backward compatible)
        goe_summary = (
            f"GOE {goe_grade.grade:+d} "
            f"({len(goe_grade.positives)} плюсов, {len(goe_grade.negatives)} минусов). "
            f"Оценка элемента: {goe_grade.estimated_score:.2f} баллов "
            f"(BV {goe_grade.base_value:.2f}"
        )
        if goe_grade.modifier:
            goe_summary += f", модификатор {goe_grade.modifier}"
        goe_summary += f"). Уверенность: {goe_grade.confidence:.0%}."
        return goe_summary

    def _determine_severity(
        self,
        value: float,
        reference_range: tuple[float, float],
    ) -> str:
        """Determine severity level for recommendation.

        Args:
            value: Metric value.
            reference_range: (min_good, max_good) range.

        Returns:
            Severity key: "too_low", "too_high", or "default".
        """
        min_good, max_good = reference_range

        if value < min_good:
            return "too_low"
        elif value > max_good:
            return "too_high"
        else:
            return "default"

    def _build_rules(self) -> None:
        """Build rule set for all element types."""
        # Add rules for each element type
        self._rules["waltz_jump"] = jump_rules.WALTZ_JUMP_RULES
        self._rules["toe_loop"] = jump_rules.TOE_LOOP_RULES
        self._rules["flip"] = jump_rules.FLIP_RULES
        self._rules["salchow"] = jump_rules.SALCHOW_RULES
        self._rules["loop"] = jump_rules.LOOP_RULES
        self._rules["lutz"] = jump_rules.LUTZ_RULES
        self._rules["axel"] = jump_rules.AXEL_RULES
        self._rules["three_turn"] = three_turn_rules.THREE_TURN_RULES
