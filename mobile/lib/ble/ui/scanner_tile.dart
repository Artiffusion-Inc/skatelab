import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../../i18n/strings.g.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/battery_indicator.dart';
import '../imu_device.dart';

class ScannerTile extends StatelessWidget {
  final ScanResult result;
  final IMUDevice? leftDevice;
  final IMUDevice? rightDevice;
  final double? voltage;
  final VoidCallback onAssign;
  final VoidCallback onSettings;

  const ScannerTile({
    super.key,
    required this.result,
    this.leftDevice,
    this.rightDevice,
    this.voltage,
    required this.onAssign,
    required this.onSettings,
  });

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    final isLeft = leftDevice?.device.remoteId == result.device.remoteId;
    final isRight = rightDevice?.device.remoteId == result.device.remoteId;
    final name = result.device.platformName;

    return ListTile(
      leading: Icon(
        Icons.bluetooth,
        color: isLeft || isRight ? AppColors.leftSide : AppColors.muted,
      ),
      title: Text(name),
      subtitle: Text(result.device.remoteId.str),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (voltage != null)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: BatteryIndicator(voltage: voltage!),
            ),
          if (isLeft)
            SideBadge(
              label: t.ble.left,
              isConnected: leftDevice?.isConnected.value ?? false,
              isLeft: true,
            )
          else if (isRight)
            SideBadge(
              label: t.ble.right,
              isConnected: rightDevice?.isConnected.value ?? false,
              isLeft: false,
            ),
          shad.GhostButton(
            onPressed: onSettings,
            size: shad.ButtonSize.small,
            child: const Icon(Icons.settings, size: 18),
          ),
        ],
      ),
      onTap: onAssign,
    );
  }
}
