import 'package:flutter/material.dart';
import '../../../i18n/strings.g.dart';
import '../../../theme/app_theme.dart';
import '../imu_device.dart';

class StatusBar extends StatelessWidget {
  final IMUDevice? leftDevice;
  final IMUDevice? rightDevice;

  const StatusBar({super.key, this.leftDevice, this.rightDevice});

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    final parts = <String>[];
    if (leftDevice != null) {
      parts.add(
        '${t.ble.left} ${leftDevice!.isConnected.value ? t.ble.status.connected : t.ble.status.disconnected}',
      );
    }
    if (rightDevice != null) {
      parts.add(
        '${t.ble.right} ${rightDevice!.isConnected.value ? t.ble.status.connected : t.ble.status.disconnected}',
      );
    }

    final leftOk = leftDevice?.isConnected.value ?? false;
    final rightOk = rightDevice?.isConnected.value ?? false;
    final color = leftOk && rightOk
        ? AppColors.statusBothConnected
        : leftOk || rightOk
        ? AppColors.statusOneConnected
        : AppColors.statusNone;

    final text = parts.isEmpty
        ? t.ble.assignHint
        : leftOk && rightOk
        ? '${parts.join('  ')}  —  ${t.ble.bothConnected}'
        : leftOk || rightOk
        ? '${parts.join('  ')}  —  ${t.ble.oneConnected}'
        : '${parts.join('  ')}  —  ${t.ble.connecting}';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      color: color,
      child: Text(text, style: const TextStyle(fontWeight: FontWeight.bold)),
    );
  }
}
