#!/usr/bin/env bash
# Automated on-device debug script for Skatelab Capture
# Usage: ./scripts/debug_on_device.sh [test_name]
#
# Prerequisites: phone connected via ADB, BLE sensor powered on
# This script installs the app, launches it, and runs automated
# UI interactions via adb shell input commands, capturing logs.

set -euo pipefail

APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
PACKAGE="ru.skatelab.capture"
ACTIVITY="${PACKAGE}/.MainActivity"
LOG_TAG="BleManager|BleScan|MainActivity|Camera2Recorder|SensorRecording"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_device() {
    if ! adb devices | grep -q "device$"; then
        log_error "No ADB device connected"
        exit 1
    fi
    log_info "Device: $(adb shell getprop ro.product.model)"
}

build_and_install() {
    log_info "Building debug APK..."
    cd "$(git rev-parse --show-toplevel)/mobile"
    GRADLE_OPTS="-Xmx6g" ./gradlew assembleDebug --max-workers=2 2>&1 | tail -3
    log_info "Installing..."
    adb install -r "$APK_PATH"
}

clear_and_launch() {
    log_info "Clearing logcat..."
    adb logcat -c
    log_info "Launching app..."
    adb shell am start -n "$ACTIVITY"
    sleep 3
}

capture_logs() {
    local duration_s="${1:-10}"
    local filter="${2:-$LOG_TAG}"
    log_info "Capturing logs for ${duration_s}s (filter: $filter)..."
    timeout "${duration_s}s" adb logcat -d 2>&1 | grep -E "$filter" || true
}

wait_for_pid() {
    for i in $(seq 1 10); do
        local pid=$(adb shell pidof "$PACKAGE" 2>/dev/null || true)
        if [ -n "$pid" ]; then
            log_info "App PID: $pid"
            return 0
        fi
        sleep 1
    done
    log_error "App failed to start"
    return 1
}

check_crash() {
    local pid=$(adb shell pidof "$PACKAGE" 2>/dev/null || true)
    if [ -z "$pid" ]; then
        log_error "APP CRASHED - process not found"
        adb logcat -d 2>&1 | grep -iE "FATAL|crash|AndroidRuntime" | tail -20
        return 1
    fi
    return 0
}

# ---- Test: BLE Scan ----
test_ble_scan() {
    log_info "=== TEST: BLE Scan ==="
    clear_and_launch
    wait_for_pid

    # Grant permissions first
    adb shell pm grant "$PACKAGE" android.permission.BLUETOOTH_SCAN 2>/dev/null || true
    adb shell pm grant "$PACKAGE" android.permission.BLUETOOTH_CONNECT 2>/dev/null || true
    adb shell pm grant "$PACKAGE" android.permission.CAMERA 2>/dev/null || true
    adb shell pm grant "$PACKAGE" android.permission.ACCESS_FINE_LOCATION 2>/dev/null || true

    # Relaunch after permission grant
    adb shell am force-stop "$PACKAGE"
    sleep 1
    clear_and_launch
    wait_for_pid

    # Tap "Scan" button — bounds [304,192][531,327], center ≈ (417, 259)
    log_info "Tapping Scan button..."
    adb shell input tap 417 259
    sleep 5

    # Check for scan results in logs
    local scan_logs=$(adb logcat -d 2>&1 | grep "Scan result:" | head -5)
    if [ -n "$scan_logs" ]; then
        log_info "BLE scan working - found devices:"
        echo "$scan_logs"
    else
        log_warn "No BLE scan results in logs"
    fi

    check_crash
}

# ---- Test: BLE Connect ----
test_ble_connect() {
    log_info "=== TEST: BLE Connect ==="
    local sensor_address="${1:-}"
    if [ -z "$sensor_address" ]; then
        log_error "Usage: $0 connect <MAC_ADDRESS>"
        log_error "  Get address from: adb logcat | grep 'Scan result'"
        exit 1
    fi

    clear_and_launch
    wait_for_pid

    # Tap Scan first — bounds [304,192][531,327], center ≈ (417, 259)
    adb shell input tap 417 259
    sleep 3

    # Tap "Left" button on device row — bounds [549,429][758,564], center ≈ (653, 496)
    log_info "Tapping Left button to connect $sensor_address..."
    adb shell input tap 653 496
    sleep 10

    # Check connection logs
    local conn_logs=$(adb logcat -d 2>&1 | grep -E "GATT state change|CONNECTED|connection" | head -10)
    if [ -n "$conn_logs" ]; then
        log_info "Connection activity:"
        echo "$conn_logs"
    else
        log_warn "No connection logs found"
    fi

    check_crash
}

# ---- Test: Permission Flow ----
test_permissions() {
    log_info "=== TEST: Permission Flow ==="
    # Revoke permissions to test request flow
    adb shell pm revoke "$PACKAGE" android.permission.BLUETOOTH_SCAN 2>/dev/null || true
    adb shell pm revoke "$PACKAGE" android.permission.BLUETOOTH_CONNECT 2>/dev/null || true
    adb shell pm revoke "$PACKAGE" android.permission.CAMERA 2>/dev/null || true

    clear_and_launch
    wait_for_pid

    # System permission dialog should appear - auto-grant after 2s
    sleep 2
    adb shell input tap 540 1200  # "While using the app" button approximate position
    sleep 2
    adb shell input tap 540 1200  # Second permission dialog
    sleep 2

    log_info "Checking if app shows BLE screen after permissions..."
    capture_logs 3 "PermissionGate|MainActivity"

    # Re-grant for other tests
    adb shell pm grant "$PACKAGE" android.permission.BLUETOOTH_SCAN 2>/dev/null || true
    adb shell pm grant "$PACKAGE" android.permission.BLUETOOTH_CONNECT 2>/dev/null || true
    adb shell pm grant "$PACKAGE" android.permission.CAMERA 2>/dev/null || true

    check_crash
}

# ---- Test: App Lifecycle ----
test_lifecycle() {
    log_info "=== TEST: App Lifecycle ==="
    clear_and_launch
    wait_for_pid

    # Background and foreground
    log_info "Sending app to background..."
    adb shell input keyevent KEYCODE_HOME
    sleep 2

    log_info "Restoring app..."
    adb shell am start -n "$ACTIVITY"
    sleep 2

    # Rotate screen
    log_info "Rotating screen..."
    adb shell settings put system accelerometer_rotation 0
    adb shell content insert --uri content://settings/system --bind name:s:user_rotation --bind value:i:1
    sleep 2
    adb shell content insert --uri content://settings/system --bind name:s:user_rotation --bind value:i:0

    check_crash
}

# ---- Test: Full Capture Flow (requires 2 sensors) ----
test_full_capture() {
    log_info "=== TEST: Full Capture Flow (manual verification) ==="
    log_warn "This test requires manual interaction with BLE sensors"
    log_info "Steps performed automatically:"
    log_info "  1. Scan for BLE devices"
    log_info "  2. You need to connect both LEFT and RIGHT sensors manually"
    log_info "  3. Navigate to Calibration → Camera → Record"

    clear_and_launch
    wait_for_pid

    # Grant permissions
    adb shell pm grant "$PACKAGE" android.permission.BLUETOOTH_SCAN 2>/dev/null || true
    adb shell pm grant "$PACKAGE" android.permission.BLUETOOTH_CONNECT 2>/dev/null || true
    adb shell pm grant "$PACKAGE" android.permission.CAMERA 2>/dev/null || true

    adb shell am force-stop "$PACKAGE"
    sleep 1
    clear_and_launch
    wait_for_pid

    # Start scan
    adb shell input tap 360 400
    sleep 5

    # From here, user needs to connect sensors manually
    log_info "Waiting 30s for manual sensor connection..."
    sleep 30

    capture_logs 5
    check_crash
}

# ---- Main ----
COMMAND="${1:-scan}"

case "$COMMAND" in
    build)
        build_and_install
        ;;
    scan)
        test_ble_scan
        ;;
    connect)
        test_ble_connect "$2"
        ;;
    permissions)
        test_permissions
        ;;
    lifecycle)
        test_lifecycle
        ;;
    full)
        test_full_capture
        ;;
    logs)
        shift
        capture_logs "${1:-10}" "${2:-$LOG_TAG}"
        ;;
    crash)
        check_crash
        if [ $? -eq 0 ]; then log_info "App is running"; fi
        ;;
    *)
        echo "Usage: $0 {build|scan|connect <MAC>|permissions|lifecycle|full|logs [duration] [filter]|crash}"
        echo ""
        echo "  build       - Build APK and install on device"
        echo "  scan        - Test BLE scanning"
        echo "  connect MAC - Test BLE connection to sensor"
        echo "  permissions - Test permission request flow"
        echo "  lifecycle   - Test background/foreground/rotation"
        echo "  full        - Full capture flow (manual sensor connection)"
        echo "  logs        - Capture filtered logs"
        echo "  crash       - Check if app crashed"
        ;;
esac
