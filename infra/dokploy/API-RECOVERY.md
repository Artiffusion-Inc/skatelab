# Current API Deployment

The restored VPS uses `dokploy-network`, not the retired `infra_app_network`.
The public website remains the separate `skatelab-site` Dokploy application.

- Source: `infra/dokploy/compose.yaml`, imported into the `skatelab-api` Compose resource in the SkateLab production environment.
- Runtime secrets: Dokploy environment; `DOKPLOY_COMPOSE_ID` and `DOKPLOY_API_KEY` in GitHub secrets.
- Ingress: native Dokploy Domain `api.skatelab.ru`, service `backend`, port 8000, HTTPS, no path stripping.
- Queue: authenticated shared Valkey, DB 4. Do not move queues or run paid processing as a deployment check.
- Deployment: manual Actions workflow builds images, triggers once, waits for Dokploy completion, then checks public health.
- Do not run the legacy global Traefik sync on this host: its routes target retired services and conflict with the live website.
- Before schema upgrades, keep a restricted PostgreSQL dump on the VPS. Backend runs Alembic before serving requests; workers wait for backend health.
- Verify `/v1/health` returns 200 JSON and unauthenticated `/v1/models` returns 401. Check container image IDs and restarts.

Rollback: set `IMAGE_TAG` in the complete preserved Dokploy environment to the last verified image SHA and deploy once. Do not downgrade the database automatically. The initial schema backup is recovery-only and must not be restored over new data without approval. Routing changes are limited to the API domain; website and shared Traefik configuration are not replaced.
