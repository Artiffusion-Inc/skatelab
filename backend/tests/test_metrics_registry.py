"""Tests for metrics_registry.py."""

import pytest
from app.metrics_registry import (
    ALL_ELEMENTS,
    CHOREO_ELEMENTS,
    JUMP_ELEMENTS,
    METRIC_REGISTRY,
    SPIN_ELEMENTS,
    STEP_ELEMENTS,
    TURN_METRIC_ELEMENTS,
    get_metrics_for_element,
)


class TestMetricRegistry:
    """Test the metric registry structure and contents."""

    def test_registry_has_all_known_metrics(self):
        """Verify all expected metrics are present."""
        expected_metrics = {
            # Jump metrics
            "airtime",
            "max_height",
            "relative_jump_height",
            "landing_knee_angle",
            "landing_knee_stability",
            "landing_trunk_recovery",
            "arm_position_score",
            "rotation_speed",
            "total_rotation_deg",
            "rotation_count",
            "under_rotation_deg",
            "jump_type",
            # Step metrics
            "knee_angle",
            "trunk_lean",
            "edge_change_smoothness",
            "spread_eagle_angle",
            "ina_bauer_score",
            "spiral_indicator",
            # Jump/spin cross-check
            "rotation_discrepancy",
            # Spin metrics
            "spin_type",
            "spin_peak_velocity",
            # Universal metrics
            "symmetry",
            # GOE-derived metrics
            "goe_score",
        }
        actual_metrics = set(METRIC_REGISTRY.keys())
        assert actual_metrics == expected_metrics, (
            f"Expected {len(expected_metrics)} metrics, "
            f"found {len(actual_metrics)}. Missing: {expected_metrics - actual_metrics}, "
            f"Extra: {actual_metrics - expected_metrics}"
        )

    def test_metric_def_fields(self):
        """Validate all required fields are present on each MetricDef."""
        for metric_name, metric_def in METRIC_REGISTRY.items():
            # Check all fields exist and have correct types
            assert hasattr(metric_def, "name"), f"{metric_name}: missing 'name'"
            assert hasattr(metric_def, "label_ru"), f"{metric_name}: missing 'label_ru'"
            assert hasattr(metric_def, "unit"), f"{metric_name}: missing 'unit'"
            assert hasattr(metric_def, "format"), f"{metric_name}: missing 'format'"
            assert hasattr(metric_def, "direction"), f"{metric_name}: missing 'direction'"
            assert hasattr(metric_def, "element_types"), f"{metric_name}: missing 'element_types'"
            assert hasattr(metric_def, "ideal_range"), f"{metric_name}: missing 'ideal_range'"

            # Type validation
            assert isinstance(metric_def.name, str), f"{metric_name}: name must be str"
            assert isinstance(metric_def.label_ru, str), f"{metric_name}: label_ru must be str"
            assert isinstance(metric_def.unit, str), f"{metric_name}: unit must be str"
            assert isinstance(metric_def.format, str), f"{metric_name}: format must be str"
            assert metric_def.direction in {"higher", "lower"}, (
                f"{metric_name}: direction must be 'higher' or 'lower'"
            )
            assert isinstance(metric_def.element_types, tuple), (
                f"{metric_name}: element_types must be tuple"
            )
            assert isinstance(metric_def.ideal_range, tuple), (
                f"{metric_name}: ideal_range must be tuple"
            )
            assert len(metric_def.ideal_range) == 2, (
                f"{metric_name}: ideal_range must have 2 values (min, max)"
            )

            # Valid unit values
            valid_units = {"s", "deg", "score", "norm", "ratio", "deg/s"}
            assert metric_def.unit in valid_units, (
                f"{metric_name}: unit '{metric_def.unit}' not in {valid_units}"
            )

    def test_jump_metrics_not_on_step_sequence(self):
        """Jump-specific metrics should not apply to a step sequence (StSq)."""
        jump_only_metrics = {"airtime", "max_height", "rotation_speed"}

        step_metrics = get_metrics_for_element("StSq1")
        step_metric_names = set(step_metrics.keys())

        for metric in jump_only_metrics:
            assert metric not in step_metric_names, (
                f"{metric} should not apply to step sequence element"
            )

    def test_symmetry_on_all_elements(self):
        """Symmetry metric should apply to all element types."""
        symmetry_def = METRIC_REGISTRY["symmetry"]
        assert set(symmetry_def.element_types) == set(ALL_ELEMENTS), (
            f"symmetry should apply to all {len(ALL_ELEMENTS)} elements. "
            f"Got: {symmetry_def.element_types}"
        )

    def test_get_metrics_for_element_jump(self):
        """Test get_metrics_for_element for an ISU jump code (3A)."""
        jump_metrics = get_metrics_for_element("3A")

        # Should have all jump-specific metrics plus symmetry
        expected_jump_metrics = {
            "airtime",
            "max_height",
            "relative_jump_height",
            "landing_knee_angle",
            "landing_knee_stability",
            "landing_trunk_recovery",
            "arm_position_score",
            "rotation_speed",
            "total_rotation_deg",
            "rotation_count",
            "rotation_discrepancy",
            "under_rotation_deg",
            "jump_type",
            "symmetry",
            "goe_score",
        }
        assert set(jump_metrics.keys()) == expected_jump_metrics

        # Verify step-specific metrics are NOT included
        step_only_metrics = {"knee_angle", "trunk_lean", "edge_change_smoothness"}
        for metric in step_only_metrics:
            assert metric not in jump_metrics

    def test_get_metrics_for_element_spin(self):
        """Test get_metrics_for_element for an ISU spin code (CSp4)."""
        spin_metrics = get_metrics_for_element("CSp4")

        # Should have spin-specific metrics plus rotation + symmetry
        expected_spin_metrics = {
            "spin_type",
            "spin_peak_velocity",
            "total_rotation_deg",
            "rotation_count",
            "rotation_discrepancy",
            "symmetry",
            "goe_score",
        }
        assert set(spin_metrics.keys()) == expected_spin_metrics

        # Verify jump-specific metrics are NOT included
        jump_only_metrics = {
            "airtime",
            "max_height",
            "landing_knee_angle",
            "under_rotation_deg",
            "jump_type",
        }
        for metric in jump_only_metrics:
            assert metric not in spin_metrics

    def test_get_metrics_for_element_step(self):
        """Test get_metrics_for_element for an ISU step sequence code (StSq1)."""
        step_metrics = get_metrics_for_element("StSq1")

        # Should have step/turn-specific metrics plus symmetry
        expected_step_metrics = {
            "knee_angle",
            "trunk_lean",
            "edge_change_smoothness",
            "spread_eagle_angle",
            "ina_bauer_score",
            "spiral_indicator",
            "symmetry",
            "goe_score",
        }
        assert set(step_metrics.keys()) == expected_step_metrics

        # Verify jump-specific metrics are NOT included
        jump_only_metrics = {
            "airtime",
            "max_height",
            "relative_jump_height",
            "landing_knee_angle",
            "landing_knee_stability",
            "landing_trunk_recovery",
            "arm_position_score",
            "rotation_speed",
        }
        for metric in jump_only_metrics:
            assert metric not in step_metrics

    def test_get_metrics_for_element_invalid(self):
        """Test get_metrics_for_element with invalid element type."""
        with pytest.raises(ValueError, match="Unknown element type"):
            get_metrics_for_element("invalid_element")

    def test_get_metrics_for_element_rejects_old_slug(self):
        """Old slug vocabulary (e.g. 'axel') must be rejected after ISU migration."""
        with pytest.raises(ValueError, match="Unknown element type"):
            get_metrics_for_element("axel")  # old slug, must be rejected

    def test_get_metrics_for_element_rejects_waltz_jump_slug(self):
        """Old slug 'waltz_jump' must be rejected after ISU migration."""
        with pytest.raises(ValueError, match="Unknown element type"):
            get_metrics_for_element("waltz_jump")

    def test_get_metrics_for_element_rejects_three_turn_slug(self):
        """Old slug 'three_turn' must be rejected after ISU migration."""
        with pytest.raises(ValueError, match="Unknown element type"):
            get_metrics_for_element("three_turn")

    def test_metric_def_is_frozen(self):
        """MetricDef should be immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError

        metric_def = METRIC_REGISTRY["airtime"]
        with pytest.raises(FrozenInstanceError):
            metric_def.name = "changed"

    def test_direction_values(self):
        """Verify direction field has valid values."""
        for metric_name, metric_def in METRIC_REGISTRY.items():
            assert metric_def.direction in {"higher", "lower"}, (
                f"{metric_name}: direction '{metric_def.direction}' is invalid"
            )

    def test_ideal_range_ordering(self):
        """Verify ideal_range has min <= max for all metrics."""
        for metric_name, metric_def in METRIC_REGISTRY.items():
            min_val, max_val = metric_def.ideal_range
            assert min_val <= max_val, (
                f"{metric_name}: ideal_range min ({min_val}) > max ({max_val})"
            )

    def test_element_types_constants(self):
        """Verify JUMP/SPIN/STEP/ALL_ELEMENTS constants are correct (ISU codes)."""
        # JUMP_ELEMENTS: 6 families x4 + 1Eu = 25
        assert len(JUMP_ELEMENTS) == 25, f"Expected 25 jump elements, got {len(JUMP_ELEMENTS)}"

        # SPIN_ELEMENTS: CSp/FSp/LSp/USp x4 + CSpB x4 = 20
        assert len(SPIN_ELEMENTS) == 20, f"Expected 20 spin elements, got {len(SPIN_ELEMENTS)}"

        # STEP_ELEMENTS: StSq1..StSq4
        assert len(STEP_ELEMENTS) == 4, f"Expected 4 step elements, got {len(STEP_ELEMENTS)}"

        # CHOREO_ELEMENTS: ChSq1
        assert len(CHOREO_ELEMENTS) == 1, f"Expected 1 choreo element, got {len(CHOREO_ELEMENTS)}"

        # ALL_ELEMENTS = jumps + spins + steps + choreo = 50
        assert len(ALL_ELEMENTS) == 50, f"Expected 50 total elements, got {len(ALL_ELEMENTS)}"
        assert JUMP_ELEMENTS + SPIN_ELEMENTS + STEP_ELEMENTS + CHOREO_ELEMENTS == ALL_ELEMENTS

        # TURN_METRIC_ELEMENTS aliases step sequences
        assert TURN_METRIC_ELEMENTS == STEP_ELEMENTS

        # No slug remnants
        for code in ALL_ELEMENTS:
            assert code != "three_turn"
            assert code != "waltz_jump"
            assert code != "axel"

        # All element types in registry should be in ALL_ELEMENTS
        for metric_def in METRIC_REGISTRY.values():
            for element_type in metric_def.element_types:
                assert element_type in ALL_ELEMENTS, (
                    f"Element type '{element_type}' not in ALL_ELEMENTS constant"
                )


def test_jump_metrics_apply_to_isu_jump_codes():
    """ISU jump code 3A exposes jump metrics (airtime + max_height)."""
    m = get_metrics_for_element("3A")
    assert "airtime" in m
    assert "max_height" in m  # jump-height metric


def test_jump_metrics_do_not_apply_to_spins():
    """ISU spin code CSp4 exposes spin metrics, not jump metrics (from brief)."""
    m = get_metrics_for_element("CSp4")
    assert "airtime" not in m
    assert "spin_peak_velocity" in m


def test_all_elements_are_isu_codes():
    """No slug remnants in ALL_ELEMENTS; StSq family present (from brief)."""
    for code in ALL_ELEMENTS:
        assert code != "three_turn"
        assert code != "waltz_jump"
    # three_turn metrics now under StSq family
    assert "StSq1" in ALL_ELEMENTS


def test_unknown_code_raises():
    """Old slug 'axel' is rejected as unknown (from brief)."""
    with pytest.raises(ValueError):
        get_metrics_for_element("axel")  # old slug, must be rejected
