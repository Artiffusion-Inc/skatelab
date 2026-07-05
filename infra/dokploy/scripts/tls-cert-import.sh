#!/usr/bin/env bash
# Import Caddy ACME certs into Traefik acme.json to avoid LE duplicate-cert
# rate limits (5/week). BLOCKER #4 fix.
#
# Usage: ./tls-cert-import.sh [caddy-cert-dir] [traefik-acme-json]
set -euo pipefail

CADDY_CERT_DIR="${1:-/opt/infra/services/caddy/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory}"
TRAEFIK_ACME="${2:-/opt/dokploy/traefik/acme.json}"

if [[ ! -d "$CADDY_CERT_DIR" ]]; then
  echo "Caddy cert dir not found: $CADDY_CERT_DIR"
  echo "Listed Caddy cert roots:"
  find /opt/infra/services/caddy/data -maxdepth 4 -type d 2>/dev/null | head -20
  exit 1
fi

if [[ -f "$TRAEFIK_ACME" ]]; then
  cp "$TRAEFIK_ACME" "$TRAEFIK_ACME.bak.$(date +%s)"
  echo "Backed up existing acme.json"
else
  echo "No existing acme.json; will create new"
  mkdir -p "$(dirname "$TRAEFIK_ACME")"
fi

# Convert Caddy PEM certs (subdomain/cert.pem + key.pem) to Traefik acme.json.
python3 <<EOF
import json, base64
from pathlib import Path

caddy_dir = Path("$CADDY_CERT_DIR")
acme_file = Path("$TRAEFIK_ACME")

data = {"letsencrypt": {"Account": {}, "Certificates": []}}
if acme_file.exists() and acme_file.stat().st_size > 0:
    try:
        data = json.loads(acme_file.read_text())
    except json.JSONDecodeError:
        print("WARN: existing acme.json unreadable, starting fresh")

certs = data.setdefault("letsencrypt", {}).setdefault("Certificates", [])
imported = 0
for cert_dir in sorted(caddy_dir.iterdir()):
    if not cert_dir.is_dir():
        continue
    domain = cert_dir.name
    # Caddy stores <domain>.crt + <domain>.key (not cert.pem/key.pem)
    cert_file = cert_dir / f"{domain}.crt"
    key_file = cert_dir / f"{domain}.key"
    if not (cert_file.exists() and key_file.exists()):
        # Fallback: some Caddy versions use cert.pem/key.pem
        cert_file = cert_dir / "cert.pem"
        key_file = cert_dir / "key.pem"
        if not (cert_file.exists() and key_file.exists()):
            continue
    cert_entry = {
        "domain": {"main": domain},
        "certificate": base64.b64encode(cert_file.read_bytes()).decode(),
        "key": base64.b64encode(key_file.read_bytes()).decode(),
    }
    certs.append(cert_entry)
    print(f"Imported: {domain}")
    imported += 1

acme_file.write_text(json.dumps(data, indent=2))
acme_file.chmod(0o600)
print(f"Wrote {acme_file} ({imported} certs)")
EOF

# Restart Traefik to load certs (Dokploy runs Traefik as a swarm service)
docker service update --force dokploy-traefik 2>/dev/null || \
  docker restart dokploy-traefik 2>/dev/null || \
  echo "NOTE: Traefik service not found — restart manually (docker service update --force dokploy-traefik)"
echo "Done"