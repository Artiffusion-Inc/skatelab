import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../../i18n/strings.g.dart';
import '../../../widgets/battery_indicator.dart';
import '../wt901_commander.dart';

class DeviceSettingsSheet extends StatelessWidget {
  final BluetoothDevice device;
  final double? voltage;
  final WT901Commander commander;
  final VoidCallback onRequestBattery;
  final VoidCallback onRenamePressed;
  final void Function(int code) onSetReturnRate;

  const DeviceSettingsSheet({
    super.key,
    required this.device,
    this.voltage,
    required this.commander,
    required this.onRequestBattery,
    required this.onRenamePressed,
    required this.onSetReturnRate,
  });

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              device.platformName,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              device.remoteId.str,
              style: TextStyle(
                fontSize: 12,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),
            _BatteryTile(voltage: voltage, onRequest: onRequestBattery),
            const shad.Divider(),
            _ReturnRateTile(onSelected: onSetReturnRate),
            ListTile(
              leading: const Icon(Icons.edit),
              title: Text(t.ble.rename.title),
              trailing: shad.SecondaryButton(
                onPressed: onRenamePressed,
                child: Text(t.ble.rename.action),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BatteryTile extends StatelessWidget {
  final double? voltage;
  final VoidCallback onRequest;
  const _BatteryTile({this.voltage, required this.onRequest});

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    return ListTile(
      leading: BatteryIndicator(voltage: voltage, iconSize: 24, fontSize: 12),
      title: Text(t.ble.battery.title),
      subtitle: Text(
        voltage == null
            ? t.ble.battery.unknown
            : '${voltage!.toStringAsFixed(2)} ${t.ble.battery.unit}',
      ),
      trailing: shad.GhostButton(
        onPressed: onRequest,
        child: Text(t.ble.battery.request),
      ),
    );
  }
}

class _ReturnRateTile extends StatelessWidget {
  final void Function(int code) onSelected;
  const _ReturnRateTile({required this.onSelected});

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    return ListTile(
      leading: const Icon(Icons.speed),
      title: Text(t.ble.returnRate.title),
      subtitle: Text(t.ble.returnRate.hint),
      trailing: DropdownButton<int>(
        value: null,
        hint: Text(t.ble.returnRate.select),
        underline: const SizedBox.shrink(),
        items: [
          DropdownMenuItem(value: 0x01, child: Text(t.ble.returnRate.hz02)),
          DropdownMenuItem(value: 0x02, child: Text(t.ble.returnRate.hz05)),
          DropdownMenuItem(value: 0x03, child: Text(t.ble.returnRate.hz1)),
          DropdownMenuItem(value: 0x04, child: Text(t.ble.returnRate.hz2)),
          DropdownMenuItem(value: 0x05, child: Text(t.ble.returnRate.hz5)),
          DropdownMenuItem(value: 0x06, child: Text(t.ble.returnRate.hz10)),
          DropdownMenuItem(value: 0x07, child: Text(t.ble.returnRate.hz20)),
          DropdownMenuItem(value: 0x08, child: Text(t.ble.returnRate.hz50)),
          DropdownMenuItem(value: 0x09, child: Text(t.ble.returnRate.hz100)),
          DropdownMenuItem(value: 0x0B, child: Text(t.ble.returnRate.hz200)),
        ],
        onChanged: (code) {
          if (code != null) onSelected(code);
        },
      ),
    );
  }
}
