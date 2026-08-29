# GitHub Automation

## Layout

- `ci.yml` delegates to `ci-reusable.yml`.
- `deploy.yml` runs full CI, builds GHCR images, then deploys production.
- `container.yml` builds Vast.ai GPU worker image.
- `mobile-*.yml` split mobile lint, tests, builds, nightly, and E2E.
- `secrets.yml` scans credentials.

## Rules

- Keep permissions least-privilege and pin supported action versions.
- CI may cancel superseded runs; production deploy must not cancel in progress.
- Preserve path filters unless changed scope is proven.
- Never print secrets or write them to summaries/artifacts.
- Reusable workflow inputs and callers must change together.
- Use `master` as deployment branch.

## Verify

```bash
actionlint .github/workflows/*.yml
uv run pytest scripts/ci-audit/ -v
```
