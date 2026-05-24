#!/usr/bin/env bash
set -euo pipefail

# Prometheus node_exporter textfile collector for Android emulator health
# Run via cron every 30s

METRIC_FILE="/var/lib/node_exporter/textfile_collector/emulator.prom"
METRIC_TMP="${METRIC_FILE}.tmp"

# Is emulator container running?
EMULATOR_UP=$(docker ps --filter name=skatelab-emulator --format '{{.Status}}' 2>/dev/null | grep -c Up || echo 0)

# Boot status
BOOT_COMPLETE=$(docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || echo 0)

# Resource usage from systemd slice
SLICE_MEM=$(systemctl show emulator.slice -p MemoryCurrent --value 2>/dev/null || echo 0)
SLICE_CPU=$(systemctl show emulator.slice -p CPUUsageNSec --value 2>/dev/null || echo 0)

cat > "${METRIC_TMP}" <<EOF
# HELP skatelab_emulator_up Whether the emulator container is running
# TYPE skatelab_emulator_up gauge
skatelab_emulator_up ${EMULATOR_UP}

# HELP skatelab_emulator_boot_complete Whether the Android VM has finished booting
# TYPE skatelab_emulator_boot_complete gauge
skatelab_emulator_boot_complete ${BOOT_COMPLETE}

# HELP skatelab_emulator_memory_bytes Current memory usage of emulator slice
# TYPE skatelab_emulator_memory_bytes gauge
skatelab_emulator_memory_bytes ${SLICE_MEM}

# HELP skatelab_emulator_cpu_ns_total CPU usage of emulator slice in nanoseconds
# TYPE skatelab_emulator_cpu_ns_total counter
skatelab_emulator_cpu_ns_total ${SLICE_CPU}
EOF

mv "${METRIC_TMP}" "${METRIC_FILE}"
