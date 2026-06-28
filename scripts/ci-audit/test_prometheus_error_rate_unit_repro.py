"""RED-by-design static assertion: prometheus error-rate unit-mismatch.

T027 / I5. `infra/prometheus/rules/recording.yml` defines
`job:inference_error_rate:percentage = (errors / total) * 100` -> a 0-100
value. `infra/prometheus/rules/alerts.yml` alerts on `> 5` (correct 5%
threshold) BUT the `HighInferenceErrorRate` description annotates with
`{{ $value | humanizePercentage }}` — Prometheus `humanizePercentage`
expects a 0-1 ratio, not a 0-100 percentage. Applied to `5.0` it renders
as "500%", then the literal `%` appends another -> broken operator display.

Contrast (proves it's the unit-mismatch outlier):
- `InferenceQueueBuildup` uses raw `{{ $value }}` (correct).
- `HighInferenceLatency` uses `humanizeDuration` on seconds (unit matches).
- `HighInferenceErrorRate` is the outlier.

This script parses both rule files READ-ONLY (PyYAML, no live prometheus)
and asserts the unit-mismatch: recording produces 0-100 via `* 100` AND
the alert description uses `humanizePercentage` (expects 0-1). Both hold
-> bug present -> exit 1 (RED).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORDING_YML = REPO_ROOT / "infra" / "prometheus" / "rules" / "recording.yml"
ALERTS_YML = REPO_ROOT / "infra" / "prometheus" / "rules" / "alerts.yml"

TARGET_RECORD = "job:inference_error_rate:percentage"
TARGET_ALERT = "HighInferenceErrorRate"

RED_MSG = (
    "RED: prometheus HighInferenceErrorRate description uses humanizePercentage "
    "(expects 0-1 ratio) on job:inference_error_rate:percentage "
    "(recording rule multiplies by 100 -> 0-100 value) -> 5% renders as 500%"
)


def _recording_expr(records: list[dict], name: str) -> str | None:
    for rule in records:
        if rule.get("record") == name:
            expr = rule.get("expr")
            return str(expr) if expr is not None else None
    return None


def _alert_description(alerts: list[dict], name: str) -> str | None:
    for rule in alerts:
        if rule.get("alert") == name:
            ann = rule.get("annotations") or {}
            desc = ann.get("description")
            return str(desc) if desc is not None else None
    return None


def main() -> int:
    recording = yaml.safe_load(RECORDING_YML.read_text())
    alerts = yaml.safe_load(ALERTS_YML.read_text())

    rec_rules = [r for g in recording.get("groups", []) for r in g.get("rules", [])]
    alert_rules = [r for g in alerts.get("groups", []) for r in g.get("rules", [])]

    expr = _recording_expr(rec_rules, TARGET_RECORD)
    if expr is None:
        print(f"FATAL: recording rule {TARGET_RECORD!r} not found")  # noqa: T201
        return 2
    desc = _alert_description(alert_rules, TARGET_ALERT)
    if desc is None:
        print(f"FATAL: alert {TARGET_ALERT!r} not found")  # noqa: T201
        return 2

    produces_0_100 = "* 100" in expr.replace("\n", " ")
    uses_humanize_pct = "humanizePercentage" in desc

    if produces_0_100 and uses_humanize_pct:
        print(RED_MSG)  # noqa: T201
        return 1

    print("GREEN: prometheus HighInferenceErrorRate unit-mismatch resolved")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
