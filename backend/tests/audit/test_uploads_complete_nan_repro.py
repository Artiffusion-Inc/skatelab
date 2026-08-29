"""#1215: int(part_number) crash on NaN part_number in /uploads/complete sorter.

The original sorter was:
    sorted(data.parts, key=lambda x: int(x["part_number"]))
A client sending part_number=NaN triggered `int(NaN) = ValueError: cannot convert
float NaN to integer`, which crashed the handler (500) and left the S3 multipart
upload dangling (no AbortMultipartUpload). #683 moved the field onto a typed
Pydantic model so a NaN payload now returns 400 at the schema boundary — but
the issue's contract is that the route explicitly guard against non-finite
part_number with `math.isfinite`, so defense in depth survives any future
loosening of the schema (e.g. switching to `float`, JSON `Infinity`, etc.).
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from app.routes.uploads import CompleteUploadRequest, UploadPart
from pydantic import ValidationError

UPLOADS_PATH = Path(__file__).resolve().parents[2] / "app" / "routes" / "uploads.py"


# ---------------------------------------------------------------------------
# Source guard — math.isfinite in the /uploads/complete handler
# ---------------------------------------------------------------------------


def test_complete_handler_has_isfinite_guard():
    """#1215: complete_upload must guard non-finite part_number via math.isfinite.

    Pydantic blocks NaN on `int` today, but defense-in-depth at the handler
    ensures the route can never 500 on a non-finite value if the schema is
    later loosened (e.g. `int = float`, JSON `Infinity`, `Decimal('nan')`,
    dict-style payloads pre-#683).
    """
    src = UPLOADS_PATH.read_text(encoding="utf-8")
    assert "math.isfinite" in src, (
        "#1215: math.isfinite guard missing from backend/app/routes/uploads.py"
    )

    # Anchor on the executable guard (not a comment) and confirm it sits inside
    # the complete_upload method body — before the `sorted(...)` call which
    # would raise on a non-finite sort key.
    guard = re.search(r"if\s+not\s+math\.isfinite\s*\(", src)
    sorted_call = re.search(r"sorted\s*\(", src)
    assert guard is not None, "expected `if not math.isfinite(...)` line in uploads.py"
    assert sorted_call is not None, "expected `sorted(...)` call in uploads.py"
    assert guard.start() < sorted_call.start(), (
        f"math.isfinite guard must come BEFORE the sorted() call. "
        f"guard_offset={guard.start()} sorted_offset={sorted_call.start()}"
    )


def test_complete_handler_guard_raises_client_exception():
    """#1215: non-finite part_number raises a 400 ClientException, not a 500 ValueError.

    Pydantic's ValidationError is a 400 by Litestar's handler chain, but if the
    guard is layered inside the handler it should raise a ClientException with
    a clear, client-actionable message — same shape as the existing part-number
    validation errors in this file.
    """
    from litestar.exceptions import ClientException
    from litestar.status_codes import HTTP_400_BAD_REQUEST

    src = UPLOADS_PATH.read_text(encoding="utf-8")
    # The guard must raise ClientException with status_code=400, not `raise
    # ValueError` (which would 500) and not a bare `pass` / silent skip
    # (which would leave a dangling multipart upload).
    guard_block = re.search(
        r"if\s+not\s+math\.isfinite\([^)]+\)\s*:\s*\n\s*raise\s+ClientException\(",
        src,
    )
    assert guard_block is not None, (
        "#1215: math.isfinite guard must raise ClientException(...), not a "
        "bare pass or generic ValueError — must surface as 400 with a clear "
        "message so the client knows to retry without NaN."
    )
    # And the status code must be 400, not 500.
    assert "HTTP_400_BAD_REQUEST" in src or "400" in src, (
        "#1215: handler must use HTTP_400_BAD_REQUEST status for non-finite "
        "part_number — anything else leaves the client without a clear fix."
    )


# ---------------------------------------------------------------------------
# Observable — NaN payload does not 500
# ---------------------------------------------------------------------------


def test_upload_part_model_rejects_nan_int():
    """Pydantic v2 rejects NaN for `int` at the schema layer (defense layer 1)."""
    with pytest.raises(ValidationError):
        UploadPart.model_validate({"part_number": float("nan"), "etag": "abc"})


def test_complete_request_rejects_nan_part_number():
    """CompleteUploadRequest rejects NaN part_number — never reaches sorted()."""
    with pytest.raises(ValidationError):
        CompleteUploadRequest.model_validate(
            {
                "upload_id": "u-1",
                "key": "uploads/1/abc/x.bin",
                "parts": [
                    {"part_number": 1, "etag": "a"},
                    {"part_number": float("nan"), "etag": "b"},
                ],
            }
        )


def test_isfinite_rejects_nan_and_inf():
    """math.isfinite is the contract: NaN, +inf, -inf all fail; reals pass."""
    assert not math.isfinite(float("nan"))
    assert not math.isfinite(float("inf"))
    assert not math.isfinite(float("-inf"))
    assert math.isfinite(0)
    assert math.isfinite(1)
    assert math.isfinite(10000)


# ---------------------------------------------------------------------------
# Regression — valid parts still sort correctly
# ---------------------------------------------------------------------------


def test_valid_parts_still_sort_and_complete():
    """#1215 regression: contiguous 1..N parts still sort + complete cleanly.

    Even after the guard is added, valid integer parts must still reach the
    S3 `complete_multipart_upload` call in ascending order.
    """
    src = UPLOADS_PATH.read_text(encoding="utf-8")
    # The S3 finalize call must remain in the handler.
    assert "complete_multipart_upload" in src, (
        "#1215: S3 complete_multipart_upload call must remain in uploads.py"
    )
    # And the parts must still be sorted before S3 completion — the guard is
    # an extra check, it does not replace the sort.
    assert "sorted(" in src, "#1215: parts must still be sorted before S3 completion"
