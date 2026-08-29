# Infrastructure

Repository-managed production deployment: Caddy, Compose, PostgreSQL, Valkey, RustFS, Prometheus, backend/frontend/arq images, and supporting services.

## Sources

- `compose.prod.yaml` — SkateLab production stack.
- `compose.yaml` — shared infrastructure stack.
- `deploy.sh` — deployment, migrations, health checks, rollback.
- `caddy/Caddyfile` — public routing and TLS.
- `.github/workflows/deploy.yml` — CI/CD orchestration.

## Rules

- Edit repository files first; never patch production as unrecorded source of truth.
- Never hardcode secrets, host credentials, keys, or `.env` contents.
- Preserve external network names and Valkey DB allocation used by production.
- RustFS requires path-style addressing and `us-east-1`.
- Format and validate Caddy before deployment.
- Never run `docker compose down --remove-orphans`, destructive volume commands, database rollback, or image cleanup without explicit approval and impact review.
- Deployment changes need health-check and rollback behavior.

## Verify

```bash
docker compose -f infra/compose.prod.yaml config
caddy fmt --diff infra/caddy/Caddyfile
caddy validate --config infra/caddy/Caddyfile
bash -n infra/deploy.sh
```

Run commands requiring unavailable local binaries in CI/container and state limitation.
