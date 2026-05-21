"""Tests for rule-based jump type classifier."""

from ml.src.analysis.jump_classifier import classify_jump

# Element names from ELEMENT_DEFS that are jumps (rotations > 0)
ELEMENT_NAMES = {
    "waltz_jump",
    "toe_loop",
    "flip",
    "salchow",
    "loop",
    "lutz",
    "axel",
}


class TestClassifyJump:
    """Test classify_jump returns correct element names and confidence."""

    def test_single_toe_loop(self):
        """Single toe loop: 1 rotation, toe pick, backward takeoff."""
        name, conf = classify_jump(
            rotation_count=1.0,
            has_toe_pick_signal=True,
            takeoff_direction="backward",
        )
        assert name in ("toe_loop", "flip", "lutz")
        assert conf > 0.5

    def test_single_axel(self):
        """Single axel: 1.5 rotations, no toe pick, forward takeoff."""
        name, conf = classify_jump(
            rotation_count=1.5,
            has_toe_pick_signal=False,
            takeoff_direction="forward",
        )
        assert name == "axel"
        assert conf > 0.5

    def test_double_axel(self):
        """Double axel: 2.5 rotations, no toe pick, forward takeoff.

        ELEMENT_DEFS only define base rotations (1 for axel = single).
        Double axel (2.5) gets diff = |2.5 - 1.5| = 1.0, no rotation bonus,
        but forward takeoff + no toe pick still identifies axel.
        """
        name, conf = classify_jump(
            rotation_count=2.5,
            has_toe_pick_signal=False,
            takeoff_direction="forward",
        )
        assert name == "axel"
        # Rotation mismatch penalizes but toe_pick + direction still identify axel
        assert conf > 0.3

    def test_triple_toe_pick_jump(self):
        """Triple toe-pick jump: 3 rotations, toe pick, backward.

        ELEMENT_DEFS only define single-jump base rotations (1.0).
        Triple (3.0) won't get rotation bonus, but toe_pick + backward
        correctly narrow to toe-pick jumps.
        """
        name, conf = classify_jump(
            rotation_count=3.0,
            has_toe_pick_signal=True,
            takeoff_direction="backward",
        )
        assert name in ("toe_loop", "flip", "lutz")
        # No rotation bonus for triple (far from base=1), but toe_pick match
        assert conf >= 0.25

    def test_triple_lutz(self):
        """Triple lutz: 3 rotations, toe pick, backward takeoff."""
        name, _conf = classify_jump(
            rotation_count=3.0,
            has_toe_pick_signal=True,
            takeoff_direction="backward",
        )
        # lutz, toe_loop, flip all have toe_pick=True and rotations=1
        # All score equally since rotation_count=3.0 is far from base=1
        assert name in ("lutz", "toe_loop", "flip")

    def test_single_salchow(self):
        """Single salchow: 1 rotation, no toe pick, backward takeoff."""
        name, conf = classify_jump(
            rotation_count=1.0,
            has_toe_pick_signal=False,
            takeoff_direction="backward",
        )
        # salchow, loop, waltz_jump all: rotations=1, no toe pick, backward
        assert name in ("salchow", "loop", "waltz_jump")
        assert conf > 0.5

    def test_single_flip(self):
        """Single flip: 1 rotation, toe pick, backward takeoff."""
        name, _conf = classify_jump(
            rotation_count=1.0,
            has_toe_pick_signal=True,
            takeoff_direction="backward",
        )
        assert name in ("flip", "toe_loop", "lutz")

    def test_toe_pick_signal_differentiates(self):
        """Toe pick signal should differentiate toe jumps from edge jumps."""
        name_toe, _conf_toe = classify_jump(
            rotation_count=1.0,
            has_toe_pick_signal=True,
            takeoff_direction="backward",
        )
        name_edge, _conf_edge = classify_jump(
            rotation_count=1.0,
            has_toe_pick_signal=False,
            takeoff_direction="backward",
        )
        # Toe-pick jumps should not be edge jumps and vice versa
        toe_pick_jumps = {"toe_loop", "flip", "lutz"}
        edge_jumps = {"salchow", "loop", "waltz_jump", "axel"}
        assert name_toe in toe_pick_jumps
        assert name_edge in edge_jumps

    def test_forward_takeoff_boosts_axel(self):
        """Forward takeoff direction should boost axel relative to backward."""
        name_fwd, conf_fwd = classify_jump(
            rotation_count=1.5,
            has_toe_pick_signal=False,
            takeoff_direction="forward",
        )
        name_bwd, conf_bwd = classify_jump(
            rotation_count=1.5,
            has_toe_pick_signal=False,
            takeoff_direction="backward",
        )
        # Forward should identify axel
        assert name_fwd == "axel"
        # Backward with same params should not prefer axel (no forward bonus)
        assert name_bwd != "axel" or conf_fwd >= conf_bwd

    def test_confidence_bounded_at_one(self):
        """Confidence should never exceed 1.0."""
        _, conf = classify_jump(
            rotation_count=1.0,
            has_toe_pick_signal=True,
            takeoff_direction="backward",
        )
        assert conf <= 1.0

    def test_confidence_non_negative(self):
        """Confidence should never be negative."""
        _, conf = classify_jump(
            rotation_count=0.0,
            has_toe_pick_signal=False,
            takeoff_direction="backward",
        )
        assert conf >= 0.0

    def test_triple_loop(self):
        """Triple loop: 3 rotations, no toe pick, backward takeoff."""
        name, _conf = classify_jump(
            rotation_count=3.0,
            has_toe_pick_signal=False,
            takeoff_direction="backward",
        )
        # No rotation bonus (3.0 far from base=1), but no toe_pick match
        # narrows to edge jumps
        assert name in ("loop", "salchow", "waltz_jump")
