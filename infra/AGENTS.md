# Infrastructure

Repository-managed production deployment: Caddy, Compose, PostgreSQL, Valkey, RustFS, Prometheus, backend/frontend/arq images, and supporting services.

## Sources

- `compose.yaml` — Dokploy-managed infrastructure stack source.
- `dokploy/scripts/dk-infra-deploy.sh` — infrastructure compose update/deploy seam.
- `dokploy/scripts/sync-traefik-config.sh` — repository-managed public API routing with rollback.
- `dokploy/scripts/health-check-poll.sh` — bounded public health gate.
- `.github/workflows/deploy.yml` — application image build and Dokploy redeploy orchestration.

## Rules

- Edit repository files first; never patch production as unrecorded source of truth.
- Never hardcode secrets, host credentials, keys, or `.env` contents.
- Preserve external network names and Valkey DB allocation used by production.
- RustFS requires path-style addressing and `us-east-1`.
- Validate Traefik before deployment and keep the previous routing files for rollback.
- Never run `docker compose down --remove-orphans`, destructive volume commands, database rollback, or image cleanup without explicit approval and impact review.
- Deployment changes need bounded public health checks and rollback behavior.

## Verify

```bash
docker compose -f infra/compose.yaml config
bash -n infra/dokploy/scripts/sync-traefik-config.sh
bash infra/dokploy/scripts/sync-traefik-config.sh --dry-run
bash infra/dokploy/scripts/health-check-poll.sh 120 5
```

Run commands requiring unavailable local binaries in CI/container and state limitation.
