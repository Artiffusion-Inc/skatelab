"""Rule-based jump type classifier using ElementDef metadata.

Classifies observed biomechanical features into ISU jump types based on
rotation count, toe pick usage, and takeoff direction.
"""

from .element_defs import ELEMENT_DEFS


def classify_jump(
    rotation_count: float,
    has_toe_pick_signal: bool,
    takeoff_direction: str = "backward",
) -> tuple[str, float]:
    """Classify jump type from biomechanical features.

    Uses ElementDef metadata (rotations, has_toe_pick, name) to score
    candidate jump types. The primary differentiators are:
    - Toe pick usage (toe_loop, flip, lutz use toe pick)
    - Takeoff direction (axel takes off forward)
    - Rotation count proximity (adjusted for axel's extra half-rotation)

    Args:
        rotation_count: Number of full rotations observed (e.g., 3.0 for triple,
            2.5 for double axel).
        has_toe_pick_signal: True if toe pick was detected in takeoff phase.
        takeoff_direction: "forward" or "backward".

    Returns:
        Tuple of (element_name, confidence) where confidence is 0.0-1.0.
    """
    candidates: list[tuple[str, float]] = []

    for elem in ELEMENT_DEFS.values():
        # Skip non-jump elements
        if elem.rotations == 0:
            continue

        score = 0.0

        # Rotation count matching.
        # elem.rotations is now float: 1.0 for single jumps, 1.5 for axel, etc.
        expected_rotations = elem.rotations

        diff = abs(rotation_count - expected_rotations)

        if diff < 0.3:
            score += 0.6
        elif diff < 0.6:
            score += 0.3

        # Toe pick matching — strong signal for classification
        if has_toe_pick_signal == elem.has_toe_pick:
            score += 0.25

        # Takeoff direction — axel takes off forward, all others backward
        if elem.name == "axel" and takeoff_direction == "forward":
            score += 0.15
        if elem.name != "axel" and takeoff_direction == "backward":
            score += 0.05

        candidates.append((elem.name, score))

    if not candidates:
        return "unknown", 0.0

    best = max(candidates, key=lambda x: x[1])
    return best[0], min(best[1], 1.0)
