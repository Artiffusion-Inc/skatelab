#!/usr/bin/env bash
# Phase 5.5: rotate critical secrets. Generates new values, prints manual steps.
# Old /opt/skatelab/.env securely deleted with shred -u after Dokploy env updated.
set -euo pipefail

echo "Generating new secrets..."
NEW_JWT=$(openssl rand -hex 32)
NEW_POSTGRES=$(openssl rand -hex 16)

echo "New JWT_SECRET_KEY: $NEW_JWT"
echo "New POSTGRES_PASSWORD: $NEW_POSTGRES"
echo ""
echo "Manual steps:"
echo "  1. Dokploy UI -> backend service env: set JWT_SECRET_KEY=$NEW_JWT"
echo "  2. Dokploy UI -> postgres service env: set POSTGRES_PASSWORD=$NEW_POSTGRES"
echo "  3. Dokploy UI -> backend env DATABASE_URL: update password to $NEW_POSTGRES"
echo "  4. Redeploy backend + postgres"
echo "  5. gh secret set JWT_SECRET_KEY --body '$NEW_JWT'"
echo "  6. gh secret set SKATELAB_DB_PASSWORD --body '$NEW_POSTGRES'"
echo "  7. After verify: sudo shred -u /opt/skatelab/.env"
echo ""
echo "WARNING: changing POSTGRES_PASSWORD requires resyncing the postgres volume"
echo "or ALTER USER password change. Prefer rotating only if volume is fresh."