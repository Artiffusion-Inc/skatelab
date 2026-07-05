#!/usr/bin/env bash
# Restrict Dokploy UI (:18080) to AmneziaWG subnet 10.99.0.0/24 only.
# Requires sudo. Idempotent — removes existing rules before re-adding.
set -euo pipefail

# Idempotent: remove old rules for :18080
iptables -D INPUT -p tcp --dport 18080 -j DROP 2>/dev/null || true
iptables -D INPUT -p tcp --dport 18080 -s 10.99.0.0/24 -j ACCEPT 2>/dev/null || true

# Allow VPN subnet first, then drop everything else
iptables -A INPUT -p tcp --dport 18080 -s 10.99.0.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 18080 -j DROP

# Persist (Debian)
if command -v netfilter-persistent &>/dev/null; then
  netfilter-persistent save
else
  echo "NOTE: netfilter-persistent not installed; rules lost on reboot. Install: apt-get install -y iptables-persistent"
fi

echo "Dokploy UI restricted to 10.99.0.0/24"
iptables -L INPUT -n -v | grep 18080