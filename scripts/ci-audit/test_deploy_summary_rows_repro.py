#!/usr/bin/env python3
"""RED-by-design repro for I2: deploy-summary table omits build-arq-worker.

Bug (I2):
    .github/workflows/deploy.yml `deploy-summary` job
    `needs: [ci, build-frontend, build-backend, build-arq-worker,
    deploy-files, deploy]` (6 entries). The markdown summary table
    (deploy-summary "Write summary" step heredoc) has only 5 rows —
    `build-arq-worker` is in `needs:` but MISSING from the table. When
    `build-arq-worker` fails, `deploy` is skipped (needs unmet) and the
    summary shows "Deploy: skipped" with NO ARQ row — the operator cannot
    see the root cause during an incident. Low-severity (observability
    only; no gating bypass).

This script parses deploy.yml read-only, extracts the deploy-summary job's
`needs:` list and the table rows in the "Write summary" step's heredoc,
and asserts every `needs:` entry has a corresponding table row. It exits
1 (RED) when the bug is present — that is the deterministic proof. After
a future fix (add the missing row), the assertion flips and the script
exits 0 (GREEN).

No live GitHub Actions runs are required.

Run:
    uv run python scripts/ci-audit/test_deploy_summary_rows_repro.py
    echo $?   # 1 = RED (bug present), 0 = GREEN (fixed)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _yaml_assert import emit, green, load_workflow, red

# Maps a `needs:` entry to the markdown-table row label that represents it.
# The deploy-summary table uses human-readable "Stage" labels, not job ids.
NEEDS_TO_LABEL = {
    "ci": "CI",
    "build-frontend": "Build Frontend",
    "build-backend": "Build Backend",
    "build-arq-worker": "Build ARQ Worker",
    "deploy-files": "Deploy Files",
    "deploy": "Deploy",
}


def _job_needs(deploy_yaml: dict, job_name: str) -> list[str]:
    jobs = deploy_yaml.get("jobs") or {}
    spec = jobs.get(job_name) or {}
    needs = spec.get("needs", []) if isinstance(spec, dict) else []
    if isinstance(needs, str):
        needs = [needs]
    return list(needs)


def _summary_step_run(jobs: dict, job_name: str) -> str:
    """Return the concatenated `run` text of the summary-writing step."""
    spec = jobs.get(job_name) or {}
    for step in spec.get("steps", []) or []:
        run_text = step.get("run") if isinstance(step, dict) else None
        if isinstance(run_text, str) and "$GITHUB_STEP_SUMMARY" in run_text:
            return run_text
    return ""


def _extract_table_rows(run_text: str) -> list[str]:
    """Extract the left-most cell of each markdown table data row.

    A data row looks like:  | Build Backend | `${{ ... }}` |
    The header row looks like: | Stage | Status | and the separator like
    |-------|--------|. We skip the header and separator by requiring the
    first cell content to be a label (not "Stage" and not all dashes).
    """
    rows = []
    for raw_line in run_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first = cells[0]
        if first.lower() == "stage":
            continue
        if set(first) <= {"-"}:
            continue
        rows.append(first)
    return rows


def main() -> int:
    deploy = load_workflow("deploy.yml")
    needs = _job_needs(deploy, "deploy-summary")
    jobs = deploy.get("jobs") or {}
    run_text = _summary_step_run(jobs, "deploy-summary")

    if not needs:
        return emit(red("RED: deploy-summary job has no `needs:` list — cannot verify."))

    if not run_text:
        return emit(red("RED: deploy-summary has no step writing to $GITHUB_STEP_SUMMARY."))

    table_rows = _extract_table_rows(run_text)
    table_set = set(table_rows)

    missing = []
    for n in needs:
        label = NEEDS_TO_LABEL.get(n, n)
        if label not in table_set:
            missing.append(n)

    if missing:
        msg = (
            "RED: deploy-summary missing table row(s) for needs entry(ies): "
            + ", ".join(missing)
            + ". The summary table omits these jobs, so their result is not "
            "visible to operators (e.g. a build-arq-worker failure hides the "
            "root cause behind a generic 'Deploy: skipped')."
        )
        return emit(red(msg))

    return emit(
        green(
            "GREEN: every deploy-summary `needs:` entry has a corresponding "
            "markdown table row — observability complete."
        )
    )


if __name__ == "__main__":
    sys.exit(main())
