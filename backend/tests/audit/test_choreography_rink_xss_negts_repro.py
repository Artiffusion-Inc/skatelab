"""RED repro tests for two backend choreography bugs.

Bug #1 (HIGH, security — SVG injection / XSS):
    rink_renderer.render_rink interpolates element `code` raw into an SVG
    `<text>` element (rink_renderer.py:106) without any XML/HTML escaping.
    The `POST /v1/choreography/render-rink` endpoint is UNAUTHENTICATED
    (no CurrentUser/VerifiedUser dependency on render_rink_diagram,
    choreography.py:264) and RenderRinkRequest.elements is `list[dict]`
    with no validation on `code` (schemas.py:615). An unauthenticated
    attacker can POST `{"code": "<script>alert(1)</script>"}` and receive
    it back verbatim inside the SVG -> reflected/stored XSS if the frontend
    inlines the SVG.

Bug #2 (MEDIUM, negative timestamps):
    csp_solver.solve_layout clamps timestamps with only an UPPER bound
    `min(target_time, duration - 5.0)` (csp_solver.py:303) and no lower
    bound. When `duration < 5.0` and peaks are present, timestamps become
    negative (duration=4.0 -> ts=-1.0; duration=0.0 -> ts=-5.0),
    breaking downstream timeline sorting/rendering and producing
    nonsensical layouts silently (no error raised).

These tests MUST be RED against current master. No production code is
modified here — only the repro tests.
"""

from __future__ import annotations

from app.services.choreography.csp_solver import solve_layout
from app.services.choreography.rink_renderer import render_rink

# ---------------------------------------------------------------------------
# Bug #1 — rink_renderer SVG injection / XSS (unescaped `code`)
# ---------------------------------------------------------------------------


def test_rink_renders_svg_with_escaped_code_no_xss():
    """render_rink must XML-escape `code`, not interpolate it raw.

    Repro: a `code` containing `<script>...</script>` is emitted verbatim
    inside the SVG `<text>` element. The render-rink route is unauthenticated,
    so this is a reflected/stored XSS sink at a trust boundary.
    """
    els = [
        {
            "code": "<script>alert(1)</script>",
            "position": {"x": 15.0, "y": 10.0},
            "timestamp": 5.0,
        }
    ]
    svg = render_rink(els)

    # CONTRACT: code must be XML-escaped, not interpolated raw (SVG XSS).
    assert "<script>" not in svg, (
        "BUG #1: rink_renderer interpolates `code` raw into SVG <text> "
        "without XML escaping — unauthenticated XSS sink at "
        "/v1/choreography/render-rink."
    )
    # After a correct escape fix, the payload should appear as entity-encoded text.
    assert "&lt;script&gt;" in svg


# ---------------------------------------------------------------------------
# Bug #2 — csp_solver negative timestamps when duration < 5.0 with peaks
# ---------------------------------------------------------------------------


def test_short_duration_with_peaks_no_negative_timestamps():
    """solve_layout must not produce negative timestamps.

    With duration=4.0 and peaks present, the upper-bound-only clamp
    `min(target_time, duration - 5.0)` yields -1.0 for every element.
    Downstream timeline rendering/sorting breaks silently.
    """
    inv = {
        "jumps": ["3Lz", "3F", "3Lo", "3S", "2A", "2T", "1Eu"],
        "spins": ["CSp4", "LSp4", "FSp4"],
        "combinations": ["3Lz+2T", "3F+2T"],
    }
    mf = {"duration": 4.0, "peaks": [10.0, 20.0], "structure": []}
    out = solve_layout(
        inventory=inv,
        music_features=mf,
        discipline="mens_singles",
        segment="free_skate",
        seed=2,
    )

    # solve_layout returns a list of layouts; collect every element timestamp.
    ts = [e["timestamp"] for layout in out for e in layout["elements"]]
    assert ts, "expected at least one layout with timestamps from this inventory"
    assert all(t >= 0.0 for t in ts), (
        f"BUG #2: negative timestamps when duration<5.0 + peaks present: {ts}"
    )
