#!/usr/bin/env bash
set -euo pipefail

# Async wrapper: fire-and-forget E2E, poll for results
# Usage: ./run-e2e-async.sh --apk-path /tmp/app-debug.apk
# Poll: cat /opt/skatelab-e2e/reports/latest-report-path.txt && test -f $(cat /opt/skatelab-e2e/reports/latest-report-path.txt)

E2E_DIR="/opt/skatelab-e2e"
REPORTS_DIR="${E2E_DIR}/reports"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${REPORTS_DIR}/maestro-${TIMESTAMP}.log"
LATEST_MARKER="${REPORTS_DIR}/latest-report-path.txt"

# Forward all args to run-e2e.sh, capture the report path
REPORT_FILE="${REPORTS_DIR}/report-${TIMESTAMP}.xml"

echo "${REPORT_FILE}" > "${LATEST_MARKER}"

nohup "${E2E_DIR}/run-e2e.sh" "$@" > "${LOG_FILE}" 2>&1 &

PID=$!
echo "E2E running in background (PID: ${PID})"
echo "Report will be at: ${REPORT_FILE}"
echo "Log: ${LOG_FILE}"
echo ""
echo "Poll for completion:"
echo "  while [ ! -f ${REPORT_FILE} ]; do sleep 5; done && echo DONE"
echo "  tail -f ${LOG_FILE}"