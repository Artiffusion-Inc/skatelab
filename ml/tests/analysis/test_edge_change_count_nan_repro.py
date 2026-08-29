"""RED repro — Issue #1279: edge_change_count silently masks NaN edge indicator
contamination.

Bug
---
`ml/src/analysis/element_segmenter.py:535` computes
`edge_change_count` as:
    features["edge_change_count"] = int(
        np.sum(np.abs(np.diff(edge_ind)) > 0.3)
    )

NaN in `edge_ind` (occluded foot / LFOOT / RFOOT) propagates through
`np.abs(NaN) = NaN`, `np.diff(NaN) = NaN`, and the critical NaN-comparison
rule `NaN > 0.3 = False`. So `np.sum(False_array) = 0` silently — the
result is plausible-looking and the analyst has no signal that the input
was corrupt. In skating, occluded frames are NORMAL during crossovers /
spins / deep leans. `edge_change_count` is a key classifier feature for
"is this a step sequence or a jump" — silent masking means a corruptly
occluded step can be misclassified with no flag.

The contract: NaN contamination in `edge_ind` must NOT silently produce a
plausible `edge_change_count`. The fix must either (a) filter NaN frames
out of the diff before summing, or (b) include a `n_nan_frames` signal
alongside the count, or (c) raise. Root-cause fix at line 535 — single
guard protects all callers (line 591 _classify_by_rules reads
`edge_change_count` to drive the three_turn branch).

These tests are written for the POST-FIX contract and FAIL on master
(RED). The fix is to add an `isfinite` guard at the computation site
(ml/src/analysis/element_segmenter.py:535).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import H36Key


def _make_segment_poses(n_frames: int, *, foot_value: float = 0.5) -> np.ndarray:
    """Build a (n_frames, 17, 2) pose array with all keypoints at a fixed
    position. Used as the base for _extract_segment_features which
    nan_to_nums the input.
    """
    poses = np.full((n_frames, 17, 2), 0.5, dtype=np.float32)
    poses[:, H36Key.LFOOT, 0] = foot_value
    poses[:, H36Key.RFOOT, 0] = foot_value
    return poses


# ---------------------------------------------------------------------------
# Test 1: SINGLE NaN in middle of edge_ind — silent zero (BUG).
# Drive the bug by patching _compute_edge_indicator to return a NaN-
# bearing signal. Pre-fix (master): line 535 silently returns 0 with no
# n_nan signal. Post-fix: features dict includes n_nan_frames > 0.
# RED on master, GREEN after fix.
# ---------------------------------------------------------------------------


def test_edge_change_count_single_nan_surfaces_nan_frames_repro(monkeypatch):
    """CORRECT behavior: with one NaN in the middle of a 5-frame edge_ind
    that contains real edge changes (>0.3 diffs), the features dict must
    surface n_nan_frames > 0 so the analyst sees the contamination.
    Pre-fix (master): `int(np.sum(np.abs(np.diff(edge_ind)) > 0.3))`
    silently returns 0 with no flag — test FAILS RED.
    """
    seg = ElementSegmenter()
    n_frames = 5
    poses = _make_segment_poses(n_frames)
    # Bypass nan_to_num at line 497 by patching the function to return
    # a NaN-bearing signal. This isolates the line 535 expression.
    monkeypatch.setattr(
        seg,
        "_compute_edge_indicator",
        lambda p: np.array([0.5, 0.6, np.nan, 0.4, 0.3], dtype=np.float32),
    )
    features = seg._extract_segment_features(poses, fps=30.0)
    n_nan = features.get("n_nan_frames", 0)
    assert n_nan >= 1, (
        f"BUG (#1279): single NaN in edge_ind silently masked. "
        f"features must include n_nan_frames >= 1 (analyst signal "
        f"for contamination), got n_nan={n_nan}. The line 535 "
        f"expression `int(np.sum(np.abs(np.diff(edge_ind)) > 0.3))` "
        f"produces a plausible-looking count with no flag for NaN "
        f"input."
    )


# ---------------------------------------------------------------------------
# Test 2: ALL-NaN edge_ind — silent zero (BUG).
# All-NaN input must surface full contamination, not silently return 0.
# ---------------------------------------------------------------------------


def test_edge_change_count_all_nan_surfaces_nan_frames_repro(monkeypatch):
    """CORRECT behavior: all-NaN edge_ind (full-segment foot occlusion)
    must surface n_nan_frames=size so the analyst sees total data loss.
    Pre-fix (master): NaN > 0.3 = False for every comparison, count=0
    silently, indistinguishable from "no edge changes" — test FAILS RED.
    """
    seg = ElementSegmenter()
    n_frames = 10
    poses = _make_segment_poses(n_frames)
    monkeypatch.setattr(
        seg,
        "_compute_edge_indicator",
        lambda p: np.full(n_frames, np.nan, dtype=np.float32),
    )
    features = seg._extract_segment_features(poses, fps=30.0)
    n_nan = features.get("n_nan_frames", 0)
    assert n_nan == n_frames, (
        f"BUG (#1279): all-NaN edge_ind silently masked. "
        f"n_nan_frames must be {n_frames} (total contamination), got "
        f"n_nan={n_nan}. The analyst has no signal that the foot "
        f"keypoints were entirely occluded."
    )


# ---------------------------------------------------------------------------
# Test 3: NaN via chain (subtle: not literal float('nan'), but
# propagated through arithmetic) — silent zero (BUG). Real-world:
# corrupted metadata yields inf-inf=NaN, not literal NaN.
# ---------------------------------------------------------------------------


def test_edge_change_count_nan_via_chain_surfaces_nan_frames_repro(monkeypatch):
    """CORRECT behavior: NaN-via-chain (inf - inf = NaN) in edge_ind
    must surface n_nan_frames just like literal NaN. Pre-fix (master):
    silently returns 0 with no signal — test FAILS RED.
    """
    seg = ElementSegmenter()
    n_frames = 4
    poses = _make_segment_poses(n_frames)
    nan_chain = np.float32(np.inf) - np.float32(np.inf)
    monkeypatch.setattr(
        seg,
        "_compute_edge_indicator",
        lambda p: np.array([0.5, 0.6, nan_chain, 0.4], dtype=np.float32),
    )
    features = seg._extract_segment_features(poses, fps=30.0)
    n_nan = features.get("n_nan_frames", 0)
    assert n_nan >= 1, (
        f"BUG (#1279): NaN-via-chain (inf-inf) in edge_ind silently "
        f"masked. n_nan_frames must be >= 1, got n_nan={n_nan}. The "
        f"`NaN > 0.3 = False` rule applies to all NaN regardless of "
        f"provenance (literal or computed)."
    )


# ---------------------------------------------------------------------------
# Test 4: regression guard — finite edge_ind with real edge changes
# must still produce correct count + n_nan=0. PASSES on master; locks
# the contract so the fix doesn't break the typical case.
# ---------------------------------------------------------------------------


def test_edge_change_count_valid_signal_unchanged_repro(monkeypatch):
    """Regression guard: a finite edge_ind with two clear edge changes
    (>0.3 diffs) must yield edge_change_count=2, n_nan=0. Stays GREEN
    on both buggy and fixed code (no NaN input). Locks the typical-case
    contract so the fix doesn't break it.
    """
    seg = ElementSegmenter()
    n_frames = 4
    poses = _make_segment_poses(n_frames)
    # 0.0, 0.5, 0.0, 0.8 → diffs 0.5, 0.5, 0.8 — all three > 0.3.
    monkeypatch.setattr(
        seg,
        "_compute_edge_indicator",
        lambda p: np.array([0.0, 0.5, 0.0, 0.8], dtype=np.float32),
    )
    features = seg._extract_segment_features(poses, fps=30.0)
    assert features["edge_change_count"] == 3, (
        f"BUG (regression): finite edge_ind with 3 diffs > 0.3 "
        f"returned count={features['edge_change_count']}, expected 3. "
        f"The fix must not change the valid-finite case."
    )
    assert features.get("n_nan_frames", 0) == 0, (
        f"BUG (regression): finite edge_ind must yield n_nan_frames=0, "
        f"got n_nan={features.get('n_nan_frames', 0)}."
    )


# ---------------------------------------------------------------------------
# Test 5: source check — root cause locked. The isfinite guard (or
# equivalent n_nan signal) must be present at line 535 in
# element_segmenter.py. RED on master, GREEN after fix.
# ---------------------------------------------------------------------------


def test_edge_change_count_isfinite_guard_source_repro():
    """GREEN contract source check: the NaN contamination in
    `edge_ind` is fixed by an `isfinite` guard at the computation site
    (ml/src/analysis/element_segmenter.py:535). Pre-fix: line 535 reads
    `int(np.sum(np.abs(np.diff(edge_ind)) > 0.3))` with no guard —
    RED. Post-fix: an `isfinite` filter on `edge_ind` AND a
    `n_nan_frames` signal in features — GREEN.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "element_segmenter.py"
    text = src_path.read_text(encoding="utf-8")
    # The buggy raw form must be gone (no unfiltered `edge_ind` diff).
    assert "int(np.sum(np.abs(np.diff(edge_ind)) > 0.3))" not in text, (
        "Source mismatch: raw `int(np.sum(np.abs(np.diff(edge_ind)) > 0.3))` "
        "still present in element_segmenter.py — the fix must filter NaN "
        "out of edge_ind before np.diff (e.g. `finite_edge = edge_ind["
        "np.isfinite(edge_ind)]` then diff `finite_edge`)."
    )
    # Post-fix: an isfinite-filtered diff and a n_nan_frames signal
    # must both be present around the edge_ind assignment.
    m = re.search(
        r"edge_ind\s*=\s*self\._compute_edge_indicator\(poses\).*?(?=\n        # |\n        return features)",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate edge_ind computation block"
    block = m.group(0)
    has_guard = (
        "isfinite(edge_ind)" in block or "np.isfinite(edge_ind)" in block
    ) and "n_nan_frames" in block
    assert has_guard, (
        "#1279 unfixed: edge_ind block has no `isfinite(edge_ind)` "
        "filter or no `n_nan_frames` signal in features. NaN in "
        "edge_ind (occluded LFOOT/RFOOT) → `NaN > 0.3 = False` → "
        "count silently plausible, no analyst signal."
    )
