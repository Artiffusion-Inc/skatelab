#!/usr/bin/env bash
# Restrict Dokploy UI (:18080) to AmneziaWG subnet 10.99.0.0/24 only.
# Swarm host-mode publish DNATs 18080 -> container:3000 in the DOCKER nat chain,
# so packets traverse FORWARD/DOCKER-USER, NOT INPUT. Block in DOCKER-USER
# matched on the conntrack-original destination port (pre-DNAT 18080).
# Requires root. Idempotent — removes existing rules before re-adding.
set -euo pipefail
export PATH=/usr/sbin:/sbin:/usr/bin:/bin:${PATH}

# Idempotent: remove old DOCKER-USER rules for the 18080 restriction
iptables -D DOCKER-USER -m conntrack --ctorigdstport 18080 -s 10.99.0.0/24 -j RETURN 2>/dev/null || true
iptables -D DOCKER-USER -m conntrack --ctorigdstport 18080 ! -s 10.99.0.0/24 -j DROP 2>/dev/null || true
# Legacy INPUT rules from earlier attempt (no-op now, but clean up if present)
iptables -D INPUT -p tcp --dport 18080 -s 10.99.0.0/24 -j ACCEPT 2>/dev/null || true
iptables -D INPUT -p tcp --dport 18080 -j DROP 2>/dev/null || true

# Allow VPN subnet first (RETURN = continue normal docker processing), then drop everything else
iptables -A DOCKER-USER -m conntrack --ctorigdstport 18080 -s 10.99.0.0/24 -j RETURN
iptables -A DOCKER-USER -m conntrack --ctorigdstport 18080 ! -s 10.99.0.0/24 -j DROP

# Persist (Debian)
if command -v netfilter-persistent &>/dev/null; then
  netfilter-persistent save
else
  echo "NOTE: netfilter-persistent not installed; rules lost on reboot. Install: apt-get install -y iptables-persistent"
fi

echo "Dokploy UI (:18080) restricted to 10.99.0.0/24 via DOCKER-USER"
iptables -L DOCKER-USER -n -v