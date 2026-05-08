import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:provider/provider.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import 'ble_manager.dart';
import 'wt901_commander.dart';
import 'ui/status_bar.dart';
import 'ui/scanner_tile.dart';
import 'ui/connection_sheet.dart';
import 'ui/device_settings_sheet.dart';
import 'ui/rename_dialog.dart';
import '../../i18n/strings.g.dart';

class BleScanScreen extends StatefulWidget {
  final VoidCallback onReady;
  const BleScanScreen({super.key, required this.onReady});

  @override
  State<BleScanScreen> createState() => _BleScanScreenState();
}

class _BleScanScreenState extends State<BleScanScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _startScan());
  }

  Future<void> _startScan() async {
    await context.read<BleManager>().startScan();
  }

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    final ble = context.watch<BleManager>();
    final devices = ble.namedScanResults;

    return Scaffold(
      appBar: AppBar(title: Text(t.ble.scanTitle)),
      body: Column(
        children: [
          StatusBar(leftDevice: ble.leftDevice, rightDevice: ble.rightDevice),
          if (!ble.isBluetoothOn)
            shad.Alert(
              leading: const Icon(Icons.bluetooth_disabled),
              title: Text(t.ble.bluetoothOff),
            ),
          if (!ble.locationPermissionGranted)
            shad.Alert(
              leading: const Icon(Icons.location_on),
              title: Text(t.permissions.bleRequired),
            ),
          if (ble.scanError != null)
            shad.Alert.destructive(
              leading: const Icon(Icons.error),
              title: Text(switch (ble.scanError!) {
                BleScanError.bluetoothOff => t.ble.bluetoothOff,
                BleScanError.locationRequired => t.ble.errors.locationRequired,
                BleScanError.unknown =>
                  ble.scanErrorMessage ?? t.ble.errors.locationRequired,
              }),
            ),
          Expanded(
            child: devices.isEmpty
                ? Center(
                    child: ble.isScanning
                        ? const CircularProgressIndicator()
                        : shad.GhostButton(
                            onPressed: _startScan,
                            leading: const Icon(Icons.refresh),
                            child: Text(t.ble.rescan),
                          ),
                  )
                : ListView.builder(
                    itemCount: devices.length,
                    itemBuilder: (ctx, i) => ScannerTile(
                      result: devices[i],
                      leftDevice: ble.leftDevice,
                      rightDevice: ble.rightDevice,
                      voltage:
                          ble.batteryLevels[devices[i].device.remoteId.str],
                      onAssign: () => _showAssignSheet(devices[i], ble),
                      onSettings: () => _showSensorSettings(devices[i], ble),
                    ),
                  ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: shad.OutlineButton(
                    onPressed: ble.isScanning ? null : _startScan,
                    leading: const Icon(Icons.search),
                    child: Text(t.ble.scan),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: shad.PrimaryButton(
                    onPressed: ble.canProceed ? widget.onReady : null,
                    leading: const Icon(Icons.arrow_forward),
                    child: Text(t.ble.next),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _showAssignSheet(ScanResult result, BleManager ble) {
    final device = result.device;
    final isLeft = ble.leftDevice?.device.remoteId == device.remoteId;
    final isRight = ble.rightDevice?.device.remoteId == device.remoteId;

    if (isLeft) {
      ble.unassignDevice('left');
      return;
    }
    if (isRight) {
      ble.unassignDevice('right');
      return;
    }

    shad.openSheet(
      context: context,
      position: shad.OverlayPosition.bottom,
      builder: (ctx) => ConnectionSheet(
        device: result.device,
        onLeft: () {
          ble.assignDevice('left', result.device);
        },
        onRight: () {
          ble.assignDevice('right', result.device);
        },
      ),
    );
  }

  void _showSensorSettings(ScanResult result, BleManager ble) {
    final commander = WT901Commander(result.device);
    shad.openSheet(
      context: context,
      position: shad.OverlayPosition.bottom,
      builder: (ctx) => DeviceSettingsSheet(
        device: result.device,
        voltage: ble.batteryLevels[result.device.remoteId.str],
        commander: commander,
        onRequestBattery: () async {
          await commander.requestBattery();
          if (ctx.mounted) Navigator.pop(ctx);
        },
        onRenamePressed: () => _showRenameDialog(result.device),
        onSetReturnRate: (code) async {
          await commander.setReturnRate(code);
          if (ctx.mounted) Navigator.pop(ctx);
        },
      ),
    );
  }

  void _showRenameDialog(BluetoothDevice device) {
    shad.showDialog(
      context: context,
      builder: (ctx) => RenameDialog(device: device),
    );
  }
}
