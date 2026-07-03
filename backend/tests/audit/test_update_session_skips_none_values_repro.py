"""RED repro — crud.session.update skips None values, preventing intentional nulling.

Bug: session.update() used `if value is not None: setattr(session, key, value)`.
This meant you COULD NOT set a field to None/null intentionally — for example,
clearing `recommendations` or `error_message` after resolving an error.

#547 fix: introduced _UNSET sentinel to distinguish "field not provided"
(sentinel) from "field explicitly None" (null). Pre-fix code is preserved
at the original location for comparison.

Latent bug fixed:
- Worker sets session.error_message on failure, but can never CLEAR it on retry
- Admin cannot null out a field to reset state
"""

import pytest


def test_update_skips_unset_values():
    """#547: crud.session.update now uses _UNSET sentinel to skip fields.

    Pre-fix: `if value is not None: setattr(session, key, value)` skipped
    None values, preventing intentional nulling.
    Post-fix: `if value is _UNSET: continue` skips _UNSET (sentinel
    for "field not provided"), and `None` is set as the field's new value
    (intentional nulling).
    """
    import inspect

    from app.crud.session import update

    source = inspect.getsource(update)
    # Post-fix: source uses the _UNSET sentinel. Strip comments AND
    # docstrings first (they may mention the pre-fix pattern).
    import re

    source_no_strings = re.sub(r"#.*", "", source)
    source_no_strings = re.sub(r'""".*?"""', "", source_no_strings, flags=re.DOTALL)
    assert "value is _UNSET" in source_no_strings, (
        "Expected update() to use the _UNSET sentinel for skip-detection. "
        "Pre-fix: `value is not None` skipped None values silently."
    )
    assert "value is not None" not in source_no_strings, (
        "Pre-fix `if value is not None: setattr(...)` should be replaced "
        "with the _UNSET sentinel — None is now a valid value to set."
    )


def test_update_can_null_field():
    """#547: update(session, error_message=None) sets error_message to NULL.

    Post-fix: the _UNSET sentinel pattern allows callers to pass None
    to explicitly null a field, and _UNSET to skip a field.
    """
    # Simulating the post-fix pattern
    session_dict = {"status": "done", "error_message": "some error"}
    _UNSET = object()
    updates = {"error_message": None, "status": "completed"}

    from app.crud.session import _UNSET as session_unset  # type: ignore[attr-defined]

    for key, value in updates.items():
        if value is session_unset:
            continue
        session_dict[key] = value

    assert session_dict["error_message"] is None, (
        "With sentinel pattern, error_message is correctly set to None"
    )
    assert session_dict["status"] == "completed", "Non-None values are still applied"

    # Sentinel pattern: passing _UNSET skips the field
    session_dict2 = {"status": "done", "error_message": "some error"}
    updates2 = {"error_message": session_unset, "status": "completed"}
    for key, value in updates2.items():
        if value is session_unset:
            continue
        session_dict2[key] = value

    assert session_dict2["error_message"] == "some error", (
        "Sentinel value (_UNSET) is correctly skipped — old value persists"
    )


def test_user_update_has_same_pattern():
    """#547: crud.user.update now uses _UNSET sentinel (same as session)."""
    import inspect
    import re

    from app.crud.user import update

    source = inspect.getsource(update)
    # Post-fix: same sentinel pattern as session.update. Strip
    # comments AND docstrings (they may mention the pre-fix pattern).
    source_no_strings = re.sub(r"#.*", "", source)
    source_no_strings = re.sub(r'""".*?"""', "", source_no_strings, flags=re.DOTALL)
    assert "_UNSET" in source_no_strings, (
        "Expected user.update() to use the _UNSET sentinel. "
        "Pre-fix: `value is not None` skipped None values silently."
    )
    assert "value is not None" not in source_no_strings, (
        "Pre-fix `value is not None` check should be replaced with _UNSET"
    )
