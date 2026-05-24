#!/usr/bin/env bash
set -euo pipefail

# Per-run: install APK, run Maestro tests, output JUnit XML
# Usage: ./run-e2e.sh --apk-path /tmp/app-debug.apk
#        ./run-e2e.sh --apk-url https://example.com/app-debug.apk
#        ./run-e2e.sh --gh-run-id 12345  # download from GitHub Actions

E2E_DIR="/opt/skatelab-e2e"
REPORTS_DIR="${E2E_DIR}/reports"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="${REPORTS_DIR}/report-${TIMESTAMP}.xml"
APK_PATH=""
MAX_RETRIES=2

while [[ $# -gt 0 ]]; do
    case $1 in
        --apk-path) APK_PATH="$2"; shift 2 ;;
        --apk-url)
            echo "Downloading APK from $2..."
            APK_PATH="/tmp/app-debug-$(date +%s).apk"
            curl -L -o "$APK_PATH" "$2"
            shift 2
            ;;
        --gh-run-id)
            echo "Downloading APK from GitHub Actions run $2..."
            APK_PATH="/tmp/app-debug-$(date +%s).apk"
            gh run download "$2" -n apk-debug -D /tmp/gh-artifacts
            APK_PATH=$(find /tmp/gh-artifacts -name '*.apk' | head -1)
            shift 2
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$APK_PATH" ] || [ ! -f "$APK_PATH" ]; then
    echo "ERROR: No APK file. Use --apk-path, --apk-url, or --gh-run-id"
    exit 1
fi

echo "APK: ${APK_PATH} ($(du -h "$APK_PATH" | cut -f1))"

# Ensure emulator is running
if ! docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
    echo "Starting emulator..."
    systemctl start skatelab-emulator.service
    echo "Waiting for boot..."
    for i in $(seq 1 24); do
        sleep 5
        if docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
            break
        fi
        echo "  Waiting... ($((i*5))s)"
    done
fi

# Install APK
echo "Installing APK..."
docker exec skatelab-emulator adb install -r "$APK_PATH" || {
    echo "Install failed, trying with -t flag..."
    docker exec skatelab-emulator adb install -r -t "$APK_PATH"
}

# Run Maestro with retry
ATTEMPT=0
while [ $ATTEMPT -le $MAX_RETRIES ]; do
    echo "Running Maestro tests (attempt $((ATTEMPT+1))/$((MAX_RETRIES+1)))..."
    if maestro test \
        --device emulator-5554 \
        --format junit \
        --output "${REPORT_FILE}" \
        "${E2E_DIR}/maestro/"; then
        echo "Maestro tests passed."
        break
    fi
    ATTEMPT=$((ATTEMPT+1))
    if [ $ATTEMPT -le $MAX_RETRIES ]; then
        echo "Attempt $ATTEMPT failed, retrying in 5s..."
        sleep 5
    else
        echo "Tests failed after $((MAX_RETRIES+1)) attempts."
        echo "Report: ${REPORT_FILE}"
        exit 1
    fi
done

# Summary
echo ""
echo "=== E2E Results ==="
if [ -f "${REPORT_FILE}" ]; then
    TOTAL=$(grep -oP 'tests="\K[0-9]+' "$REPORT_FILE" | head -1)
    FAILURES=$(grep -oP 'failures="\K[0-9]+' "$REPORT_FILE" | head -1)
    echo "Tests: ${TOTAL}, Failures: ${FAILURES:-0}"
    echo "Report: ${REPORT_FILE}"
fi
