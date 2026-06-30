# Merge fix-all-open-issues bug fixes (#442–#447)

## Objective

Land the already-implemented fixes for open bug issues #442, #443, #444, #445, #446, #447 onto `master` via a PR, get CI green, merge, and close the six issues. Issue #349 (enhancement, spin level detection) is explicitly out of scope for this tranche and remains open.

## Original Request

«давай поставим цель исправить все issues» — clarified scope via intake: "Слить готовые фиксы + закрыть issues" (merge the ready fixes + close issues). The bug fixes were already implemented in worktree `fix-442-444-auth-error-detail` before this goal was set.

## Intake Summary

- Input shape: `existing_plan` (work already done: 9 commits, 6 bugs, RED→GREEN proven locally)
- Audience: SkateLab repo (Artiffusion-Inc/skatelab), operator (Michael)
- Authority: `requested`
- Proof type: `test` (CI green on the PR) + `decision` (PR merged, issues closed)
- Completion proof: PR merged into `master`, CI conclusion=success on the merge commit, GitHub issues #442–#447 closed.
- Goal oracle: `gh pr view <PR> --json state,mergedAt` = MERGED with CI green; `gh issue list --state open --search "442 443 444 445 446 447"` returns none of the six.
- Likely misfire: declaring success after opening the PR (not merged) or after local GREEN (CI may fail on ruff/biome/ktlint/mobile CI gates not run locally); or closing issues before the fixes actually ship on master.
- Blind spots considered: CI gates beyond what was run locally (full backend pytest, mobile CI build, frontend biome+tsc+vitest); the worktree branch already has 9 commits — must push from the worktree branch, not master; merge strategy (squash vs merge) per repo convention; the existing `fix-all-open-issues` goal dir has notes from prior tranches (#416/#417) — do not conflate.
- Existing plan facts: 9 commits on branch `worktree-fix-442-444-auth-error-detail`, origin/master at `563286bb`. Commits: RED repro + fix for each of #443/#445/#446/#447; combined mobile RED repro + fix for #442/#444. Local verification done: backend pytest (rate-limit + analyzer-save + auth routes 42 passed), mobile shared+androidApp testDebugUnitTest GREEN, androidApp ktlint GREEN, frontend vitest 84/84 + tsc clean, ruff clean. Repro tests copied from sibling branch `worktree-backend-save-audit` (commits 3f3a7f0f / b44cfd6d / be04f8cf / 4fc1394b / 7bacc20b).

## Goal Oracle

The oracle for this goal is:

`gh pr list --state merged --head worktree-fix-442-444-auth-error-detail` shows the PR MERGED, the latest master CI run conclusion=success, and `gh issue view 442..447 --json state` all show CLOSED.

The PM must keep comparing task receipts to this oracle. A pushed branch, an open PR, or a passing local run is not enough. The goal finishes only when the fixes are on master with green CI and the six issues are closed.

## Goal Kind

`existing_plan`

## Current Tranche

The implementation work is complete and locally verified. The remaining work is the finishing-branch slice: push the worktree branch to origin, open a PR against `master` with "Что сделано" / "Как проверить" sections covering #442–#447, watch CI to green (fix any CI-only gate failures inside the worktree), merge, close the six issues. This is one coherent finishing slice, not a discovery goal.

## Non-Negotiable Constraints

- All work and the PR come from the worktree branch `worktree-fix-442-444-auth-error-detail`; never commit on master directly (worktree mandate).
- PR base = `master`; title and description follow commit/PR conventions.
- Do NOT touch issue #349 (enhancement, out of scope) — leave it open.
- RED-repro tests stay in the PR (they are now GREEN; they are the regression guard, not dropped).
- If CI reveals a gate not run locally (e.g. full backend pytest regression, mobile CI assembleDebug, frontend biome check), fix it in the same worktree branch — do not merge red.

## Stop Rule

Stop only when a final Judge/PM audit proves: PR merged to master, master CI green, issues #442–#447 closed. Do not stop after pushing or opening the PR. Do not close issues before the merge lands.

## Slice Sizing

This tranche is a single finishing-branch slice (push → PR → CI green → merge → close issues). It is the largest safe useful slice and it is bounded and reversible until merge.