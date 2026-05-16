#!/usr/bin/env python3
# ruff: noqa: T201, PLW0602, PLW0603, ARG001, BLE001, S110, SIM105, ERA001
"""Fix WT901 IMU sensor with ACC=[0,0,0] by sending recovery commands via BLE from Linux.

Usage:
    python scripts/fix_wt901_acc.py [MAC_ADDRESS] [--reset-only]

If MAC not provided, defaults to E8:17:15:8A:70:15 (known broken sensor).
--reset-only: Only send factory reset, skip reconfiguration.
"""

import argparse
import asyncio
import struct
import sys

from bleak import BleakClient, BleakScanner

# WT901 BLE UUIDs (must match Android BleManager)
SERVICE_UUID = "0000ffe5-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9b34fb"
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"

# Known sensor MACs
SENSOR_RIGHT = "E8:17:15:8A:70:15"  # The one with ACC=[0,0,0]
SENSOR_LEFT = "E5:CA:10:1D:BC:0B"  # Working sensor

# WT901 command format: FF AA <reg> <data_len> <data...>
# But Android sends 5-byte: FF AA <b3> <b4> <b5>
# where b3=register, b4+b5=data (2 bytes, little-endian)


def cmd_unlock() -> bytes:
    """Unlock register for configuration (10-second window)."""
    return bytes([0xFF, 0xAA, 0x69, 0x88, 0xB5])


def cmd_stop_calibration() -> bytes:
    """Stop active ACC/MAG calibration."""
    return bytes([0xFF, 0xAA, 0x01, 0x01, 0x00])


def cmd_factory_reset() -> bytes:
    """Factory reset — restore all registers to defaults."""
    return bytes([0xFF, 0xAA, 0x00, 0xFF, 0x00])


def cmd_output_content(value: int = 0x0046) -> bytes:
    """Set OutputContent register (0x02). Default 0x0046 = ACC+GYRO+Quaternion."""
    return bytes([0xFF, 0xAA, 0x02, value & 0xFF, (value >> 8) & 0xFF])


def cmd_output_rate(rate_code: int = 0x09) -> bytes:
    """Set OutputRate register (0x03). Default 0x09 = 100Hz."""
    return bytes([0xFF, 0xAA, 0x03, rate_code, 0x00])


def cmd_save() -> bytes:
    """Save config to EEPROM."""
    return bytes([0xFF, 0xAA, 0x00, 0x00, 0x00])


notification_count = 0
acc_samples = []
frame_data = []


def parse_frame_header(data: bytearray) -> str | None:
    """Parse WT901 frame header byte to identify content."""
    if len(data) < 2:
        return None
    header = data[0]
    # 0x55 = time frame, 0x61 = combined (ACC+GYRO+Angle/Euler)
    # Other headers possible but 0x61 is the most useful
    if header == 0x61:
        return "combined"
    elif header == 0x55:
        return "time"
    return f"0x{header:02x}"


def notification_handler(sender, data: bytearray):
    """Handle BLE notifications to verify ACC data."""
    global notification_count, acc_samples, frame_data
    notification_count += 1

    if notification_count <= 10:
        frame_data.append(data.hex())

    # 0x61 = combined frame: header(1) + len(1) + ACC(6) + GYRO(6) + Euler(6) = 20 bytes
    if len(data) >= 20 and data[0] == 0x61 and notification_count <= 100:
        # ACC: bytes 2-7 (3 x int16, little-endian)
        ax = struct.unpack_from("<h", data, 2)[0] / 32768.0 * 16  # ±16g range
        ay = struct.unpack_from("<h", data, 4)[0] / 32768.0 * 16
        az = struct.unpack_from("<h", data, 6)[0] / 32768.0 * 16

        acc_samples.append((ax, ay, az))
        if notification_count <= 20:
            print(f"  Frame {notification_count}: ACC=[{ax:.3f}, {ay:.3f}, {az:.3f}] g")


async def scan_wt901(timeout: float = 10.0):
    """Scan for WT901 BLE devices."""
    print(f"Scanning for WT901 devices ({timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    wt901_devices = []
    for d in devices:
        name = (d.name or "").upper()
        addr = d.address.upper()
        if "WT901" in name or "WIT" in name or addr.startswith("E8:17") or addr.startswith("E5:CA"):
            wt901_devices.append(d)
            print(f"  Found: {d.address} ({d.name or 'Unknown'})")
    if not wt901_devices:
        print("No WT901 devices found. All BLE devices:")
        for d in sorted(devices, key=lambda x: x.rssi if hasattr(x, "rssi") and x.rssi else -999):
            print(f"  {d.address} ({d.name or 'Unknown'}) RSSI={getattr(d, 'rssi', '?')}")
    return wt901_devices


def evaluate_acc(samples: list[tuple[float, float, float]], label: str = "") -> str:
    """Evaluate ACC samples and return status."""
    if not samples:
        print(f"  No ACC samples received ({label})")
        return "NO_DATA"

    avg_ax = sum(s[0] for s in samples) / len(samples)
    avg_ay = sum(s[1] for s in samples) / len(samples)
    avg_az = sum(s[2] for s in samples) / len(samples)
    print(f"\n  ACC {label} (avg of {len(samples)} samples):")
    print(f"  AX={avg_ax:.3f}g  AY={avg_ay:.3f}g  AZ={avg_az:.3f}g")

    if abs(avg_az) > 1.0:
        print("  ✓ ACC is working — reading gravity correctly!")
        return "OK"
    elif abs(avg_ax) < 0.01 and abs(avg_ay) < 0.01 and abs(avg_az) < 0.01:
        print("  ✗ ACC still [0,0,0] — likely hardware damage")
        return "ZERO"
    else:
        print("  ? ACC has non-zero values but may be off")
        return "PARTIAL"


async def fix_sensor(mac_address: str, reset_only: bool = False, max_retries: int = 5):
    """Connect to WT901 and send recovery commands."""
    global notification_count, acc_samples, frame_data
    notification_count = 0
    acc_samples = []
    frame_data = []

    client = None
    for attempt in range(1, max_retries + 1):
        print(f"\nConnecting to {mac_address} (attempt {attempt}/{max_retries})...")
        try:
            client = BleakClient(mac_address, timeout=15.0)
            await client.connect()
            print(f"  Connected! MTU: {client.mtu_size}")
            break
        except Exception as e:
            print(f"  Connection failed: {e}")
            if attempt < max_retries:
                wait = 2.0 * attempt
                print(f"  Retrying in {wait}s... (disconnect Android app if connected)")
                # Remove from Linux Bluetooth cache
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "bluetoothctl",
                        "remove",
                        mac_address,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.wait()
                except Exception:
                    pass
                await asyncio.sleep(wait)
            else:
                print(f"\n  Could not connect after {max_retries} attempts.")
                print("  Solutions:")
                print("  1. Force-stop Android app: adb shell am force-stop ru.skatelab.capture")
                print("  2. Disable Bluetooth on phone temporarily")
                print("  3. Power-cycle the sensor")
                return False

    if not client or not client.is_connected:
        return False

    try:
        # Enable notifications
        print("\nEnabling notifications...")
        await client.start_notify(NOTIFY_UUID, notification_handler)
        await asyncio.sleep(1.0)

        # Check initial ACC
        print("\n[1/6] Reading initial ACC data...")
        notification_count = 0
        acc_samples = []
        await asyncio.sleep(2.0)
        evaluate_acc(acc_samples, "initial")

        # Step 2: Stop any ongoing calibration
        print("\n[2/6] Stopping calibration...")
        await client.write_gatt_char(WRITE_UUID, cmd_stop_calibration(), response=False)
        await asyncio.sleep(0.5)

        # Step 3: Factory reset
        print("[3/6] Factory reset (FF AA 00 FF 00)...")
        await client.write_gatt_char(WRITE_UUID, cmd_factory_reset(), response=False)
        print("  Waiting 3s for reset...")
        await asyncio.sleep(3.0)

        # Re-enable notifications (reset may have cleared them)
        try:
            await client.start_notify(NOTIFY_UUID, notification_handler)
        except Exception:
            pass
        await asyncio.sleep(1.0)

        # Step 4: Check ACC after factory reset
        print("\n[4/6] Checking ACC after factory reset...")
        notification_count = 0
        acc_samples = []
        await asyncio.sleep(2.0)
        reset_status = evaluate_acc(acc_samples, "after factory reset")

        if reset_only:
            print("\n--reset-only: skipping reconfiguration")
            print("Sensor is now at factory defaults. Reconnect via Android app to reconfigure.")
            return reset_status == "OK"

        # Step 5: Reconfigure (WITHOUT accCalibrate)
        print("\n[5/6] Reconfiguring sensor (no ACC calibration)...")

        # Unlock
        await client.write_gatt_char(WRITE_UUID, cmd_unlock(), response=False)
        await asyncio.sleep(0.05)
        # OutputContent: ACC+GYRO+Quaternion (0x0046)
        await client.write_gatt_char(WRITE_UUID, cmd_output_content(0x0046), response=False)
        await asyncio.sleep(0.1)
        # OutputRate: 100Hz (0x09)
        await client.write_gatt_char(WRITE_UUID, cmd_output_rate(0x09), response=False)
        await asyncio.sleep(0.1)
        # Save
        await client.write_gatt_char(WRITE_UUID, cmd_save(), response=False)
        await asyncio.sleep(0.5)

        # Step 6: Verify final output
        print("[6/6] Verifying final ACC output...")
        notification_count = 0
        acc_samples = []
        await asyncio.sleep(3.0)
        final_status = evaluate_acc(acc_samples, "final")

        if final_status == "OK":
            print("\n✓ SENSOR FIXED! ACC is reading gravity correctly.")
            return True
        elif final_status == "ZERO":
            print("\n✗ ACC still [0,0,0] — hardware may be permanently damaged.")
            print("  Try power-cycling the sensor and running this script again.")
            return False
        else:
            print("\n? ACC has values but may need investigation.")
            return False

    finally:
        if client and client.is_connected:
            await client.disconnect()
            print("\nDisconnected from sensor.")


async def main():
    parser = argparse.ArgumentParser(description="Fix WT901 IMU sensor ACC via BLE")
    parser.add_argument("mac", nargs="?", default=SENSOR_RIGHT, help="Sensor MAC address")
    parser.add_argument(
        "--reset-only", action="store_true", help="Only factory reset, skip reconfiguration"
    )
    parser.add_argument("--scan", action="store_true", help="Only scan for devices, don't connect")
    args = parser.parse_args()

    mac = args.mac.upper()

    if args.scan:
        await scan_wt901()
        return

    print("WT901 ACC Fix Tool")
    print(f"Target: {mac}")
    if args.reset_only:
        print("Mode: factory reset only (skip reconfiguration)")

    try:
        success = await fix_sensor(mac, reset_only=args.reset_only)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nError: {e}")
        print("\nScanning for nearby devices...")
        await scan_wt901()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
