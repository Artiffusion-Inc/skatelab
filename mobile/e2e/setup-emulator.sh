#!/usr/bin/env bash
set -euo pipefail

# One-time setup: install Maestro CLI, copy docker-compose + systemd files
# Run: ./setup-emulator.sh

E2E_DIR="/opt/skatelab-e2e"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== SkateLab E2E Setup ==="

# Install Maestro CLI
if ! command -v maestro &>/dev/null; then
    echo "Installing Maestro CLI..."
    curl -Ls "https://get.maestro.mobile.dev" | bash
    echo "Maestro installed: $(maestro --version)"
else
    echo "Maestro already installed: $(maestro --version)"
fi

# Install GitHub CLI for artifact downloads
if ! command -v gh &>/dev/null; then
    echo "Installing GitHub CLI..."
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
        dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
        tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    apt-get update && apt-get install gh -y
    echo "gh installed: $(gh --version)"
else
    echo "gh already installed: $(gh --version)"
fi

# Create E2E directory
mkdir -p "${E2E_DIR}/reports"
mkdir -p "${E2E_DIR}/flows"

# Copy docker-compose and scripts
cp "${SCRIPT_DIR}/docker-compose.yml" "${E2E_DIR}/"
cp "${SCRIPT_DIR}/run-e2e.sh" "${E2E_DIR}/"
cp "${SCRIPT_DIR}/run-e2e-async.sh" "${E2E_DIR}/"
cp "${SCRIPT_DIR}/metrics.sh" "${E2E_DIR}/"
cp -r "${SCRIPT_DIR}/maestro/" "${E2E_DIR}/maestro/"

chmod +x "${E2E_DIR}"/*.sh

# Install systemd units
cp "${SCRIPT_DIR}/systemd/emulator.slice" /etc/systemd/system/
cp "${SCRIPT_DIR}/systemd/skatelab-emulator.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable skatelab-emulator.service

# Start emulator
echo "Starting emulator container..."
systemctl start skatelab-emulator.service

# Wait for emulator boot
echo "Waiting for emulator to boot..."
timeout=120
elapsed=0
while ! docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; do
    sleep 5
    elapsed=$((elapsed + 5))
    if [ $elapsed -ge $timeout ]; then
        echo "ERROR: Emulator did not boot within ${timeout}s"
        exit 1
    fi
    echo "  Waiting... (${elapsed}s)"
done

echo "Emulator booted. Saving named snapshot..."
docker exec skatelab-emulator adb shell avd snapshot save with_app_installed

echo ""
echo "=== Setup Complete ==="
echo "Emulator:  systemctl status skatelab-emulator.service"
echo "Run tests:  ${E2E_DIR}/run-e2e.sh --apk-path /tmp/app-debug.apk"
echo "Async run:  ${E2E_DIR}/run-e2e-async.sh --apk-path /tmp/app-debug.apk"
