# ci-audit — RED-by-design static-assertion repro scripts

Deterministic, offline repro scripts that PROVE two CI infra bugs are
structurally present in the checked-in GitHub Actions workflow YAML. They
do **not** require live GitHub Actions runs, network access, or `gh` calls
— they parse `.github/workflows/*.yml` read-only and assert on the
workflow structure.

## Design: RED-by-design

Each script asserts **the bug is present**. When the bug is structurally
detected, the script prints a `RED: <bug> ...` message and exits `1`. That
non-zero exit is the deterministic proof — the test "fails" because the bug
exists. This is the inverse of a normal unit test but exactly right for a
repro that must remain RED until a fix lands.

After the corresponding fix is applied to the workflow YAML, the assertion
flips and the script exits `0` (GREEN). These scripts are intended to be
re-run after the fix PR to confirm the structural change, then retired (or
converted into a normal GREEN regression guard).

## The two bugs

### I1 — `test_mobile_e2e_trigger_repro.py`
`mobile-e2e.yml` and `mobile-ci.yml` both trigger on `push: branches:
[master]` and run in parallel with no `workflow_run` trigger and no
`needs:` linkage. The e2e "Download APK" step runs
`gh run list --workflow=mobile-ci.yml --status=success --limit=1`, which on
a fresh push of commit N returns N-1's run (mobile-ci for N is still
in_progress). Maestro flows from commit N run against the APK from commit
N-1 — a one-commit coverage lag on every push.

### I2 — `test_deploy_summary_rows_repro.py`
`deploy.yml` `deploy-summary` job `needs: [ci, build-frontend,
build-backend, build-arq-worker, deploy-files, deploy]` (6 entries) but
the markdown summary table has only 5 rows — `build-arq-worker` is in
`needs:` but missing from the table. When `build-arq-worker` fails,
`deploy` is correctly skipped (needs unmet) but the summary shows
"Deploy: skipped" with no ARQ row, hiding the root cause. Low-severity,
observability-only.

## Run

```sh
uv run python scripts/ci-audit/test_mobile_e2e_trigger_repro.py
echo $?   # 1 = RED (bug present), 0 = GREEN (fixed)

uv run python scripts/ci-audit/test_deploy_summary_rows_repro.py
echo $?   # 1 = RED (bug present), 0 = GREEN (fixed)
```

`_yaml_assert.py` is a small shared helper (YAML load + RED/GREEN emit).
PyYAML is resolved via the repo `uv` environment (`uv run python ...`).

## Scope

These scripts are **diagnosis only**. They do **not** edit any workflow
YAML and do **not** fix the bugs — the fix is a separate later tranche.
The scripts are not wired into any CI workflow, so they do not affect the
pipeline. The local `exit=1` runs are the proof.