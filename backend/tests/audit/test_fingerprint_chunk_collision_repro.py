"""Repro tests — fingerprint.compute_fingerprint fallback reads only first 256KB
chunk → prefix collision (#847).

``compute_fingerprint`` (fingerprint.py:30-37) fallback path (chromaprint
unavailable) iterates ``f.read(262144)`` chunks but breaks after the FIRST
chunk because ``if h.digest_size > 0: break`` — ``h.digest_size`` is a constant
property of SHA-256 (=32), always >0, so the guard fires after one chunk.
Two files sharing a 256KB prefix but differing after collide.

Fix (#847): remove the first-chunk-only guard. ``iter(lambda: f.read(262144),
b"")`` already terminates on EOF.

Tests:
  - observable: two files with shared 256KB prefix + different tails must
    produce DIFFERENT fingerprints (RED: same).
  - observable: a large file (>256KB) fingerprint must depend on bytes beyond
    the first chunk (RED: tail ignored).
  - source-asserting: compute_fingerprint fallback has no ``digest_size`` guard.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from app.services.choreography.fingerprint import compute_fingerprint


@pytest.fixture
def tmp_audio_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_compute_fingerprint_distinct_tails_distinct_hashes_repro(tmp_audio_dir: Path):
    """#847: two files sharing a 256KB+ prefix but with different tails must
    NOT collide on fingerprint.

    RED without the fix: the first-chunk-only guard fires after the first
    262144-byte chunk, so the tail is never hashed → identical fp.
    """
    prefix = b"X" * 300_000  # > 262144 chunk, so tail is in chunk 2+
    a = tmp_audio_dir / "a.mp3"
    b = tmp_audio_dir / "b.mp3"
    a.write_bytes(prefix + b"AAA-tail-A")
    b.write_bytes(prefix + b"BBB-different-tail-1234567890")

    fa = compute_fingerprint(str(a))
    fb = compute_fingerprint(str(b))
    assert fa is not None and fb is not None
    assert fa != fb, (
        f"#847: prefix collision — distinct tails hashed to same fingerprint "
        f"{fa!r}. compute_fingerprint only reads the first 262144-byte chunk."
    )


def test_compute_fingerprint_tail_bytes_affect_hash_repro(tmp_audio_dir: Path):
    """#847: bytes beyond the first 256KB chunk must contribute to the hash.

    RED without the fix: changing a byte at offset 300_000 does not change the
    fingerprint (tail never read).
    """
    prefix = b"Y" * 300_000
    a = tmp_audio_dir / "x.mp3"
    b = tmp_audio_dir / "y.mp3"
    a.write_bytes(prefix + b"tail-one")
    b.write_bytes(prefix + b"tail-two")

    fa = compute_fingerprint(str(a))
    fb = compute_fingerprint(str(b))
    assert fa != fb, (
        "#847: tail bytes (offset >262144) do not affect fingerprint — "
        "fallback only hashes the first chunk."
    )


def test_compute_fingerprint_source_no_digest_size_guard_repro():
    """#847 GREEN (root cause lock): compute_fingerprint source must NOT contain
    the ``digest_size`` guard that breaks after the first chunk.
    """
    import inspect

    from app.services.choreography import fingerprint as fp_mod

    src = inspect.getsource(fp_mod.compute_fingerprint)
    assert "digest_size" not in src, (
        "#847: compute_fingerprint still has the first-chunk-only guard based "
        "on digest_size (a constant) — it always breaks after the first chunk, "
        "leaving the tail unhashed. Remove the guard."
    )
