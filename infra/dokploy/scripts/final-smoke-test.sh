#!/usr/bin/env bash
# End-to-end validation of all migrated services + security headers + TLS certs.
# Run after Phase 4 Traefik cutover.
set -euo pipefail

DOMAINS=(
  "https://skatelab.ru"
  "https://api.skatelab.ru/v1/health"
  "https://rss.skatelab.ru"
  "https://feeds.skatelab.ru"
  "https://search.skatelab.ru"
  "https://ntfy.skatelab.ru"
  "https://9r.skatelab.ru"
  "https://ov.skatelab.ru"
  "https://qbit.skatelab.ru"
  "https://dav.skatelab.ru"
  "https://mqtt.skatelab.ru"
  "https://mf.skatelab.ru"
  "https://s3.skatelab.ru"
  "https://s3c.skatelab.ru"
  "https://sub.skatelab.ru"
)

PASS=0; FAIL=0
echo "=== Final smoke test ==="
for d in "${DOMAINS[@]}"; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 "$d" || echo "000")
  if [[ "$code" =~ ^(200|301|302)$ ]]; then
    echo "PASS: $d ($code)"; PASS=$((PASS+1))
  else
    echo "FAIL: $d ($code)"; FAIL=$((FAIL+1))
  fi
done
echo ""
echo "Passed: $PASS/${#DOMAINS[@]}  Failed: $FAIL/${#DOMAINS[@]}"

echo "=== Security headers ==="
for d in "https://skatelab.ru" "https://api.skatelab.ru"; do
  echo "$d:"
  curl -sI "$d" | grep -E "Strict-Transport-Security|X-Frame-Options|X-Content-Type-Options|Referrer-Policy" || echo "  MISSING HEADERS"
done

echo "=== TLS cert expiry ==="
for d in skatelab.ru api.skatelab.ru; do
  expiry=$(echo | openssl s_client -servername "$d" -connect "$d:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  echo "$d: expires $expiry"
done

[[ $FAIL -gt 0 ]] && exit 1
echo "All checks complete"