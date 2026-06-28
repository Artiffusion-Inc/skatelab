#!/usr/bin/env python3
"""RED-by-design repro for I1: mobile-e2e tests the PREVIOUS commit's APK.

Bug (I1):
    .github/workflows/mobile-e2e.yml triggers on `push: branches: [master]`
    (paths-filtered). .github/workflows/mobile-ci.yml triggers on the SAME
    push. There is NO `workflow_run` trigger and NO `needs:` linkage between
    them. The e2e "Download APK" step runs
    `gh run list --workflow=mobile-ci.yml --status=success --limit=1` —
    on a fresh push of commit N, mobile-ci for N is still in_progress, so
    this returns N-1's run. Maestro flows from commit N run against the APK
    built from commit N-1. Deterministic on every push.

This script parses both workflow YAMLs read-only and asserts the race is
STRUCTURALLY present. It exits 1 (RED) when the bug is present — that is
the deterministic proof. After a future fix (workflow_run trigger or
needs: linkage + non-stale fetch), the assertions flip and the script
exits 0 (GREEN).

No live GitHub Actions runs are required.

Run:
    uv run python scripts/ci-audit/test_mobile_e2e_trigger_repro.py
    echo $?   # 1 = RED (bug present), 0 = GREEN (fixed)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _yaml_assert import emit, green, load_workflow, red


def _has_workflow_run_trigger(on_field) -> bool:
    """True if the workflow has an `on.workflow_run` trigger."""
    if isinstance(on_field, str):
        return False
    if isinstance(on_field, dict):
        return "workflow_run" in on_field
    if isinstance(on_field, list):
        return any(isinstance(item, dict) and "workflow_run" in item for item in on_field)
    return False


def _workflow_run_references(on_field, target_workflow: str) -> bool:
    """True if an `on.workflow_run` trigger references target_workflow.

    GitHub Actions uses the plural key ``workflow_run.workflows`` (a list),
    but older docs/specs sometimes mention a singular ``workflow``. Accept
    either key so the oracle matches the real schema.
    """
    if isinstance(on_field, dict):
        wr = on_field.get("workflow_run")
        if isinstance(wr, dict):
            wfs = wr.get("workflows", wr.get("workflow"))
            if isinstance(wfs, str):
                return wfs == target_workflow
            if isinstance(wfs, list):
                return target_workflow in wfs
        return False
    if isinstance(on_field, list):
        return any(_workflow_run_references(item, target_workflow) for item in on_field)
    return False


def _job_needs(jobs: dict) -> dict:
    """Map job_name -> its needs list (or [] if none)."""
    out = {}
    for name, spec in (jobs or {}).items():
        needs = (spec or {}).get("needs", []) if isinstance(spec, dict) else []
        if isinstance(needs, str):
            needs = [needs]
        out[name] = needs
    return out


def _has_stale_fetch(e2e_yaml: dict) -> bool:
    """True if any step run-text uses `gh run list ... --status=success`."""
    jobs = e2e_yaml.get("jobs") or {}
    for _jname, jspec in jobs.items():
        for step in (jspec or {}).get("steps", []) or []:
            run_text = step.get("run") if isinstance(step, dict) else None
            if isinstance(run_text, str):
                joined = " ".join(run_text.split())
                if "gh run list" in joined and "--status=success" in joined:
                    return True
    return False


def main() -> int:
    e2e = load_workflow("mobile-e2e.yml")
    ci = load_workflow("mobile-ci.yml")

    on_e2e = e2e.get("on")
    has_wr = _has_workflow_run_trigger(on_e2e)
    wr_refs_ci = _workflow_run_references(on_e2e, "mobile-ci.yml")

    # needs: linkage — any e2e job depending on a mobile-ci job name.
    # mobile-ci job names: changes, lint, test, build, mobile-ci-passed.
    ci_job_names = set(_job_needs(ci.get("jobs") or {}).keys())
    e2e_needs = _job_needs(e2e.get("jobs") or {})
    has_needs_linkage = any(
        any(n in ci_job_names for n in needs_list) for needs_list in e2e_needs.values()
    )

    stale_fetch = _has_stale_fetch(e2e)

    # GREEN contract (per brief): a workflow_run trigger referencing
    # mobile-ci.yml OR a `needs:` linkage to a mobile-ci job, AND no stale
    # `gh run list --status=success` fetch. The trigger/linkage link the two
    # workflows so e2e runs after mobile-ci; the stale-fetch removal ensures
    # the APK comes from the triggering run, not the previous commit's run.
    has_linkage = (has_wr and wr_refs_ci) or has_needs_linkage

    reasons = []
    if not has_wr:
        reasons.append("no `on.workflow_run` trigger")
    elif not wr_refs_ci:
        reasons.append("`on.workflow_run` does not reference mobile-ci.yml")
    if not has_linkage:
        reasons.append("no `workflow_run`/`needs:` linkage to a mobile-ci run")
    if stale_fetch:
        reasons.append("`gh run list --status=success` stale-fetch present")

    if reasons:
        msg = (
            "RED: stale-APK race structurally present in mobile-e2e.yml — "
            + "; ".join(reasons)
            + ". e2e runs in parallel with mobile-ci on the same push and "
            "downloads the latest *successful* (N-1) APK, not the current "
            "commit's APK."
        )
        return emit(red(msg))

    return emit(
        green(
            "GREEN: mobile-e2e.yml is triggered after mobile-ci completes "
            "(workflow_run/needs linkage) and/or no stale-fetch — stale-APK "
            "race absent."
        )
    )


if __name__ == "__main__":
    sys.exit(main())
