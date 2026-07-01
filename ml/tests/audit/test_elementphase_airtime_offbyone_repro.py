"""RED repro — ElementPhase.airtime_frames / airtime_sec inclusive-end off-by-one (#518).

types.py:478  airtime_frames  = self.landing - self.takeoff        (SPAN, missing +1)
types.py:489  airtime_sec     = (self.landing - self.takeoff) / fps (SPAN, missing +1)

`landing` is a CONCRETE INCLUSIVE frame index:
- types.py:464 docstring: "Landing frame (0 for steps/turns)" — concrete index.
- physics_engine.py:631  com[takeoff_idx : landing_idx + 1, 1] — the +1 in the
  Python slice confirms landing_idx is the inclusive last flight frame.
- physics_engine.py:641  np.arange(flight_frames + 1) — same inclusive convention.

A flight from takeoff=20 to landing=28 spans 9 INCLUSIVE frames (20,21,...,28).
airtime_frames must be 9 (count), but the span formula gives 28-20 = 8. The
airtime is undercounted by one frame, and the airtime_sec is one frame short,
which can drop a just-valid jump below a downstream plausibility gate.

Sibling of #516 (ElementSegment.duration_frames) — same inclusive-end span-vs-
count class, different property.

This test MUST fail (RED) against the current code. Repro, not a fix.
"""

from src.types import ElementPhase


def test_airtime_frames_counts_inclusive_landing():
    """A flight takeoff=20 → landing=28 spans 9 inclusive frames (20..28).
    airtime_frames must be 9, not 8.
    """
    phase = ElementPhase(
        name="jump",
        start=0,
        takeoff=20,
        peak=24,
        landing=28,
        end=44,
    )
    assert phase.airtime_frames == 9, (
        f"BUG #518: airtime_frames = {phase.airtime_frames} for takeoff=20, "
        f"landing=28 (9 inclusive frames 20..28), expected 9. types.py:478 "
        f"returns self.landing - self.takeoff (span 8), but `landing` is an "
        f"INCLUSIVE frame index (physics_engine.py:631 slices "
        f"com[takeoff:landing+1] knowing inclusive). Fix: +1."
    )


def test_airtime_sec_counts_inclusive_landing():
    """airtime_sec for takeoff=20 → landing=28 at fps=30 is 9/30 = 0.3 s, not
    8/30 = 0.267 s.
    """
    phase = ElementPhase(
        name="jump",
        start=0,
        takeoff=20,
        peak=24,
        landing=28,
        end=44,
    )
    airtime = phase.airtime_sec(fps=30.0)
    assert airtime == 0.3, (
        f"BUG #518: airtime_sec = {airtime} for takeoff=20, landing=28 at "
        f"fps=30 (9 frames = 0.3 s), expected 0.3. types.py:489 returns "
        f"(landing-takeoff)/fps = 8/30 = 0.267 (span), but `landing` is "
        f"inclusive → count is 9. Fix: (landing-takeoff+1)/fps."
    )
