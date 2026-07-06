"""#642: task_ttl_seconds=0 silently deletes keys via EXPIRE/SETEX.

Redis EXPIRE with seconds=0 deletes the key immediately.
Pydantic validator must reject ttl <= 0 at config level.
"""

from __future__ import annotations

import pytest
from app.config import AppConfig
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Source guard — validator exists in config
# ---------------------------------------------------------------------------


def test_task_ttl_validator_exists_in_source():
    """#642: AppConfig.task_ttl_seconds has a field_validator rejecting <= 0."""
    import inspect

    source = inspect.getsource(AppConfig)
    assert "task_ttl_seconds" in source, "task_ttl_seconds field missing from AppConfig"
    assert "_ttl_positive" in source, "#642 validator _ttl_positive not found in AppConfig"


# ---------------------------------------------------------------------------
# Validator rejects invalid values
# ---------------------------------------------------------------------------


def test_task_ttl_zero_rejected():
    """#642: task_ttl_seconds=0 raises ValidationError."""
    with pytest.raises(ValidationError, match="task_ttl_seconds must be > 0"):
        AppConfig(task_ttl_seconds=0)


def test_task_ttl_negative_rejected():
    """#642: task_ttl_seconds=-1 raises ValidationError."""
    with pytest.raises(ValidationError, match="task_ttl_seconds must be > 0"):
        AppConfig(task_ttl_seconds=-1)


# ---------------------------------------------------------------------------
# Valid values still accepted
# ---------------------------------------------------------------------------


def test_task_ttl_valid_accepted():
    """#642: task_ttl_seconds=3600 (valid) is accepted."""
    s = AppConfig(task_ttl_seconds=3600)
    assert s.task_ttl_seconds == 3600


def test_task_ttl_default_accepted():
    """#642: default task_ttl_seconds is valid."""
    s = AppConfig()
    assert s.task_ttl_seconds == 86400
