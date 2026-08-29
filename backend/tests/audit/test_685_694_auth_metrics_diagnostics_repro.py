"""RED→GREEN repro tests for issues #685–#694.

Covers:
  #685: login() does not check is_active
  #686: reset_password() does not revoke refresh tokens
  #687: register() logs as 'login' event
  #688: refresh() race on last_used_at (atomic mark_used)
  #689: _set_auth_cookies hardcodes domain=skatelab.ru
  #691: get_prs no order_by (already fixed, verify)
  #692: check_stagnation/variability NaN mean propagates
  #693: check_new_pr doesn't validate latest_value is finite
  #694: get_trend date_filter tz-aware vs naive TypeError
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

AUTH_PATH = BACKEND_ROOT / "app" / "routes" / "auth.py"
METRICS_PATH = BACKEND_ROOT / "app" / "routes" / "metrics.py"
DIAG_PATH = BACKEND_ROOT / "app" / "services" / "diagnostics.py"
CONFIG_PATH = BACKEND_ROOT / "app" / "config.py"
REFRESH_TOKEN_CRUD_PATH = BACKEND_ROOT / "app" / "crud" / "refresh_token.py"


def _load_module(path: Path, name: str = "_mod"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# #685: login() must check is_active
# ---------------------------------------------------------------------------


def test_685_login_checks_is_active():
    """login() must reject deactivated (is_active=False) users with 403."""
    src = AUTH_PATH.read_text(encoding="utf-8")
    # Must have an is_active check in login()
    login_block_start = src.find("async def login(")
    assert login_block_start != -1, "login() not found in auth.py"
    # Find the end of login method (next method def)
    next_def = src.find("\n    async def ", login_block_start + 1)
    next_def2 = src.find("\n    @post", login_block_start + 1)
    login_end = min(x for x in [next_def, next_def2, len(src)] if x > login_block_start)
    login_block = src[login_block_start:login_end]
    assert "is_active" in login_block, (
        "#685: login() must check user.is_active and reject deactivated "
        "accounts. No is_active check found in login() block."
    )
    assert "Account disabled" in login_block or "account disabled" in login_block.lower(), (
        "#685: login() must raise 403 with 'Account disabled' message when is_active is False."
    )


# ---------------------------------------------------------------------------
# #686: reset_password() must revoke all refresh tokens
# ---------------------------------------------------------------------------


def test_686_reset_password_revokes_tokens():
    """reset_password() must call revoke_all_for_user after password change."""
    src = AUTH_PATH.read_text(encoding="utf-8")
    reset_block_start = src.find("async def reset_password(")
    assert reset_block_start != -1, "reset_password() not found in auth.py"
    next_def = src.find("\n    async def ", reset_block_start + 1)
    next_def2 = src.find("\n    @post", reset_block_start + 1)
    reset_end = min(x for x in [next_def, next_def2, len(src)] if x > reset_block_start)
    reset_block = src[reset_block_start:reset_end]
    assert "revoke_all_for_user" in reset_block, (
        "#686: reset_password() must call revoke_all_for_user(db, user.id) "
        "to invalidate all sessions after password change."
    )


def test_686_revoke_all_for_user_exists():
    """revoke_all_for_user must exist in refresh_token CRUD."""
    src = REFRESH_TOKEN_CRUD_PATH.read_text(encoding="utf-8")
    assert "revoke_all_for_user" in src, (
        "#686: revoke_all_for_user function must exist in refresh_token CRUD."
    )


# ---------------------------------------------------------------------------
# #687: register() must log as 'register', not 'login'
# ---------------------------------------------------------------------------


def test_687_register_logs_register_event():
    """register() must log 'register' event, not 'login'."""
    src = AUTH_PATH.read_text(encoding="utf-8")
    reg_block_start = src.find("async def register(")
    assert reg_block_start != -1, "register() not found in auth.py"
    next_def = src.find("\n    async def ", reg_block_start + 1)
    next_def2 = src.find("\n    @post", reg_block_start + 1)
    reg_end = min(x for x in [next_def, next_def2, len(src)] if x > reg_block_start)
    reg_block = src[reg_block_start:reg_end]
    assert '"register"' in reg_block, (
        "#687: register() must log auth event as 'register', not 'login'. "
        "Found 'login' event in register block instead."
    )
    # Ensure no 'login' event in register block (it was the bug)
    login_events = re.findall(r'log_auth_event\(.*?"login"', reg_block)
    assert len(login_events) == 0, (
        f"#687: register() must not log 'login' event. Found: {login_events}"
    )


# ---------------------------------------------------------------------------
# #688: refresh() must use atomic mark_used
# ---------------------------------------------------------------------------


def test_688_refresh_uses_atomic_mark():
    """refresh() must use mark_used_atomic instead of mark_used for race safety."""
    src = AUTH_PATH.read_text(encoding="utf-8")
    refresh_block_start = src.find("async def refresh(")
    assert refresh_block_start != -1, "refresh() not found in auth.py"
    next_def = src.find("\n    async def ", refresh_block_start + 1)
    next_def2 = src.find("\n    @post", refresh_block_start + 1)
    refresh_end = min(x for x in [next_def, next_def2, len(src)] if x > refresh_block_start)
    refresh_block = src[refresh_block_start:refresh_end]
    assert "mark_used_atomic" in refresh_block, (
        "#688: refresh() must use mark_used_atomic for atomic last_used_at update. "
        "Non-atomic mark_used creates a read-modify-write race."
    )


def test_688_mark_used_atomic_exists():
    """mark_used_atomic must exist in refresh_token CRUD."""
    src = REFRESH_TOKEN_CRUD_PATH.read_text(encoding="utf-8")
    assert "mark_used_atomic" in src, (
        "#688: mark_used_atomic function must exist in refresh_token CRUD."
    )


# ---------------------------------------------------------------------------
# #689: _set_auth_cookies must not hardcode domain
# ---------------------------------------------------------------------------


def test_689_no_hardcoded_domain():
    """_set_auth_cookies and _clear_auth_cookies must use settings, not hardcoded 'skatelab.ru'."""
    src = AUTH_PATH.read_text(encoding="utf-8")
    # Count occurrences of hardcoded domain in cookie definitions
    hardcoded = src.count('domain="skatelab.ru"') + src.count("domain='skatelab.ru'")
    assert hardcoded == 0, (
        f"#689: found {hardcoded} hardcoded domain='skatelab.ru' in auth.py. "
        "Must use settings.app.cookie_domain (None for dev, '.skatelab.ru' for prod)."
    )


def test_689_cookie_domain_in_config():
    """AppConfig must have cookie_domain field."""
    src = CONFIG_PATH.read_text(encoding="utf-8")
    assert "cookie_domain" in src, (
        "#689: AppConfig must include cookie_domain setting (None for dev)."
    )


def test_689_set_cookies_uses_settings():
    """_set_auth_cookies must reference cookie_domain from settings."""
    src = AUTH_PATH.read_text(encoding="utf-8")
    set_cookies_start = src.find("def _set_auth_cookies(")
    assert set_cookies_start != -1
    next_def = src.find("\n    def ", set_cookies_start + 1)
    set_cookies_end = next_def if next_def != -1 else len(src)
    set_cookies_block = src[set_cookies_start:set_cookies_end]
    assert "cookie_domain" in set_cookies_block, (
        "#689: _set_auth_cookies must use settings.app.cookie_domain, not a hardcoded string."
    )


# ---------------------------------------------------------------------------
# #691: get_prs must order_by (already fixed, verify)
# ---------------------------------------------------------------------------


def test_691_prs_has_order_by():
    """get_prs must order by created_at desc to return newest PR first."""
    src = METRICS_PATH.read_text(encoding="utf-8")
    prs_block_start = src.find("async def get_prs(")
    assert prs_block_start != -1, "get_prs() not found in metrics.py"
    next_def = src.find("\n    async def ", prs_block_start + 1)
    next_def2 = src.find("\n    @get", prs_block_start + 1)
    prs_end = min(x for x in [next_def, next_def2, len(src)] if x > prs_block_start)
    prs_block = src[prs_block_start:prs_end]
    assert "order_by" in prs_block, (
        "#691: get_prs must have order_by to ensure deterministic newest-first PR."
    )


# ---------------------------------------------------------------------------
# #692: check_stagnation/variability must filter NaN
# ---------------------------------------------------------------------------


def test_692_stagnation_filters_nan():
    """check_stagnation must filter NaN/inf before computing mean."""
    src = DIAG_PATH.read_text(encoding="utf-8")
    stagnation_start = src.find("def check_stagnation(")
    assert stagnation_start != -1
    next_def = src.find("\ndef ", stagnation_start + 1)
    stagnation_block = src[stagnation_start : next_def if next_def != -1 else len(src)]
    assert "math.isfinite" in stagnation_block, (
        "#692: check_stagnation must filter NaN/inf before computing mean."
    )


def test_692_variability_filters_nan():
    """check_high_variability must filter NaN/inf before computing mean."""
    src = DIAG_PATH.read_text(encoding="utf-8")
    var_start = src.find("def check_high_variability(")
    assert var_start != -1
    next_def = src.find("\ndef ", var_start + 1)
    var_block = src[var_start : next_def if next_def != -1 else len(src)]
    assert "math.isfinite" in var_block, (
        "#692: check_high_variability must filter NaN/inf before computing mean."
    )


def test_692_stagnation_nan_returns_none():
    """Stagnation with NaN in values returns None (not NaN in message)."""
    mod = _load_module(DIAG_PATH)
    result = mod.check_stagnation(
        element="jumps",
        metric="airtime",
        values=[1.0, float("nan"), 1.01, 0.99, 1.0, 1.01, 0.98],
        metric_label="Время в воздухе",
    )
    # With NaN filtered out, we have 6 finite values, CV very low → stagnation finding
    # OR if < 5 finite values, returns None. Either way: no NaN in result.
    if result is not None:
        assert "nan" not in result.detail.lower(), (
            f"#692: stagnation finding must not contain NaN, got: {result.detail}"
        )


def test_692_variability_nan_returns_none_or_clean():
    """High variability with NaN in values returns clean result (no NaN)."""
    mod = _load_module(DIAG_PATH)
    result = mod.check_high_variability(
        element="jumps",
        metric="airtime",
        values=[1.0, 5.0, float("nan"), 10.0, 0.5, 8.0, 3.0, 15.0],
        metric_label="Время в воздухе",
    )
    if result is not None:
        assert "nan" not in result.detail.lower(), (
            f"#692: variability finding must not contain NaN, got: {result.detail}"
        )


# ---------------------------------------------------------------------------
# #693: check_new_pr must validate latest_value is finite
# ---------------------------------------------------------------------------


def test_693_new_pr_rejects_nan():
    """check_new_pr must return None when latest_value is NaN."""
    mod = _load_module(DIAG_PATH)
    result = mod.check_new_pr(
        element="jumps",
        metric="airtime",
        is_latest_pr=True,
        metric_label="Воздух",
        latest_value=float("nan"),
        prev_best=0.5,
    )
    assert result is None, f"#693: check_new_pr must return None for NaN latest_value, got {result}"


def test_693_new_pr_rejects_inf():
    """check_new_pr must return None when latest_value is inf."""
    mod = _load_module(DIAG_PATH)
    result = mod.check_new_pr(
        element="jumps",
        metric="airtime",
        is_latest_pr=True,
        metric_label="Воздух",
        latest_value=float("inf"),
        prev_best=0.5,
    )
    assert result is None, f"#693: check_new_pr must return None for inf latest_value, got {result}"


def test_693_new_pr_source_guard():
    """Source must have math.isfinite check before rendering latest_value."""
    src = DIAG_PATH.read_text(encoding="utf-8")
    pr_start = src.find("def check_new_pr(")
    assert pr_start != -1
    next_def = src.find("\ndef ", pr_start + 1)
    pr_block = src[pr_start : next_def if next_def != -1 else len(src)]
    assert "math.isfinite" in pr_block, (
        "#693: check_new_pr must validate latest_value with math.isfinite before rendering."
    )


def test_693_new_pr_finite_works():
    """check_new_pr still works for finite values after the guard."""
    mod = _load_module(DIAG_PATH)
    result = mod.check_new_pr(
        element="jumps",
        metric="airtime",
        is_latest_pr=True,
        metric_label="Воздух",
        latest_value=0.85,
        prev_best=0.7,
    )
    assert result is not None, "check_new_pr must fire for valid finite latest_value"
    assert "0.850" in result.detail


# ---------------------------------------------------------------------------
# #694: get_trend date_filter must not mix tz-aware with tz-naive
# ---------------------------------------------------------------------------


def test_694_trend_uses_naive_cutoff():
    """get_trend must strip timezone from cutoff to avoid TypeError with naive DB columns."""
    src = METRICS_PATH.read_text(encoding="utf-8")
    trend_block_start = src.find("async def get_trend(")
    assert trend_block_start != -1, "get_trend() not found in metrics.py"
    next_def = src.find("\n    async def ", trend_block_start + 1)
    next_def2 = src.find("\n    @get", trend_block_start + 1)
    trend_end = min(x for x in [next_def, next_def2, len(src)] if x > trend_block_start)
    trend_block = src[trend_block_start:trend_end]
    # Must strip tz info so comparison works with both tz-aware and tz-naive columns
    assert "replace(tzinfo=None)" in trend_block or "replace(tzinfo" in trend_block, (
        "#694: get_trend must produce a naive-datetime cutoff "
        "(.replace(tzinfo=None)) so it compares correctly with "
        "tz-naive DB columns (SQLite TIMESTAMP WITHOUT TIME ZONE)."
    )
