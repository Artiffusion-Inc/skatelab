"""Repro test — choreography music upload fingerprint dedup IDOR (#840).

``POST /choreography/music/upload`` (routes/choreography.py) deduplicates a
byte-identical upload by SHA256 fingerprint GLOBALLY — returning another
user's ``music_id`` + ``filename`` without an ownership check. A user B who
happens to upload the same bytes as user A receives A's record, leaking both
the existence and the (potentially sensitive) filename of A's upload, and
handing B a ``music_id`` they can turn into a 403-oracle via
``/choreography/generate``.

Every OTHER music route (get_music_analysis, generate_layout, export_program,
delete_program) already enforces ``music.user_id != user.id``. The dedup
return path is the only music-path without it.

Fix (#840): scope ``find_music_by_fingerprint`` to the caller's ``user_id`` —
a cross-user hit is treated as a miss, falling through to a new row for the
current user. Cross-user dedup-by-content is not a feature; it violates the
trust boundary.

Tests:
  - behavioral: upload with a fingerprint that only ANOTHER user owns must
    fall through to create (music_id is a fresh row for the caller), NOT
    return the victim's music_id.
  - source-asserting: crud filters by ``user_id`` when given; route passes
    ``user_id=verified_user.id``.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.routes.choreography import ChoreographyController

# Mock aiobotocore before importing (mirrors test_choreography_upload.py).
_mock_aiobotocore = MagicMock()
_mock_aiobotocore_session = MagicMock()
sys.modules["aiobotocore"] = _mock_aiobotocore
sys.modules["aiobotocore.session"] = _mock_aiobotocore_session

controller = object.__new__(ChoreographyController)


def _bound(name):
    handler = getattr(controller, name)
    return handler.fn.__get__(controller, ChoreographyController)


@pytest.fixture
def attacker_user():
    u = MagicMock()
    u.id = "user_b_attacker"
    return u


@pytest.fixture
def victim_music():
    """A completed music record owned by user A (the victim)."""
    m = MagicMock()
    m.id = "music_user_a_private"
    m.filename = "my-competition-program-2026-final.mp3"
    m.user_id = "user_a_victim"
    return m


@pytest.fixture
def attacker_music():
    """A fresh row created for user B (the attacker) when dedup correctly misses."""
    m = MagicMock()
    m.id = "music_user_b_new"
    m.filename = "upload.mp3"
    return m


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.app.state.arq_pool = AsyncMock()
    return req


@pytest.fixture
def mock_file():
    f = MagicMock()
    f.filename = "upload.mp3"
    f.read = AsyncMock(return_value=b"shared bytes")
    return f


@pytest.fixture
def mock_tmp():
    tmp = MagicMock()
    tmp.name = "/tmp/upload.mp3"
    tmp.write = MagicMock()
    tmp.__enter__ = MagicMock(return_value=tmp)
    tmp.__exit__ = MagicMock(return_value=False)
    return tmp


@pytest.mark.asyncio
async def test_fingerprint_dedup_cross_user_treated_as_miss(
    attacker_user, victim_music, attacker_music, mock_request, mock_file, mock_tmp
):
    """#840: a byte-identical upload whose only completed fingerprint hit belongs
    to ANOTHER user must fall through to a new row for the caller — NOT return
    the victim's music_id/filename.

    RED without the fix: the route's ``find_music_by_fingerprint(db, fp)``
    query is global, so it returns ``victim_music``; the route returns
    ``UploadMusicResponse(music_id="music_user_a_private", ...)`` — a direct
    cross-user leak. After the fix (scope to ``user_id=verified_user.id``):
    the cross-user hit is a miss → fall through → ``create_music_analysis``
    for the attacker.
    """
    with (
        patch(
            "app.routes.choreography.find_music_by_fingerprint",
            new_callable=AsyncMock,
            return_value=None,  # the fix makes the cross-user hit a miss
        ) as mock_find,
        patch(
            "app.routes.choreography.create_music_analysis",
            new_callable=AsyncMock,
            return_value=attacker_music,
        ) as mock_create,
        patch("app.routes.choreography.upload_file"),
        patch("app.routes.choreography.update_music_analysis"),
        patch("app.routes.choreography.tempfile.NamedTemporaryFile", return_value=mock_tmp),
        patch("app.routes.choreography.asyncio.to_thread", new_callable=AsyncMock),
    ):
        resp = await _bound("upload_music")(mock_request, attacker_user, AsyncMock(), mock_file)

    # The caller must get their OWN new record, not the victim's.
    assert resp.music_id == attacker_music.id, (
        f"#840 IDOR: fingerprint dedup returned {resp.music_id!r} (expected "
        f"the caller's own new row {attacker_music.id!r}). The route leaked "
        f"another user's music_id by treating a cross-user fingerprint hit as "
        f"a match."
    )
    # And find_music_by_fingerprint must have been called scoped to the caller.
    assert mock_find.await_count == 1
    _, kwargs = mock_find.call_args
    assert kwargs.get("user_id") == attacker_user.id, (
        f"#840: find_music_by_fingerprint was called without the caller's "
        f"user_id scope (kwargs={kwargs}); the cross-user hit is not filtered "
        f"out."
    )


def test_source_find_music_by_fingerprint_filters_by_user_id():
    """#840: crud.find_music_by_fingerprint must accept user_id and filter on it."""
    import inspect

    from app.crud.choreography import find_music_by_fingerprint

    sig = inspect.signature(find_music_by_fingerprint)
    assert "user_id" in sig.parameters, (
        "#840: find_music_by_fingerprint must accept a user_id parameter to "
        "scope the dedup query to the caller."
    )
    src = inspect.getsource(find_music_by_fingerprint)
    assert "MusicAnalysis.user_id" in src, (
        "#840: find_music_by_fingerprint must filter on MusicAnalysis.user_id "
        "when user_id is given."
    )


def test_source_upload_route_passes_user_id_to_find():
    """#840: the upload route must pass user_id=verified_user.id into the
    fingerprint lookup so the cross-user hit is excluded. Call may span lines."""
    import re
    from pathlib import Path

    src = Path(__import__("app.routes.choreography", fromlist=["__file__"]).__file__).read_text(
        encoding="utf-8"
    )
    assert re.search(
        r"find_music_by_fingerprint\(\s*db\s*,\s*fingerprint\s*,\s*user_id\s*=\s*verified_user\.id\s*\)",
        src,
    ), "#840: the upload route must scope find_music_by_fingerprint to the caller's user_id."
