"""Personal record detection logic."""

import math


def check_pr(
    direction: str,
    current_best: float | None,
    new_value: float,
) -> tuple[bool, float | None]:
    """Check if new_value is a personal record.

    Args:
        direction: "higher" (bigger is better) or "lower" (smaller is better).
        current_best: Previous best value, or None if no history.
        new_value: The new metric value to check.

    Returns:
        (is_pr, prev_best) where prev_best is the old best if it's a PR.
    """
    # #629: NaN/inf must never be a PR. Guard BEFORE the `current_best is None`
    # early-return — otherwise a missing-data first session silently marks NaN
    # as PR, triggers `check_new_pr` diagnostic on a NaN value, and stores
    # is_pr=True in DB.
    if not math.isfinite(new_value):
        return False, current_best

    if current_best is None:
        return True, None

    if direction == "higher":
        is_pr = new_value > current_best
    else:
        is_pr = new_value < current_best

    return is_pr, current_best if is_pr else None
