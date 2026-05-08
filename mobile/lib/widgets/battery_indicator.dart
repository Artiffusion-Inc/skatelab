import 'package:flutter/material.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../theme/app_theme.dart';

/// Compact battery indicator: icon + voltage label.
/// Used in scanner tiles, top bars, device sheets.
class BatteryIndicator extends StatelessWidget {
  final double? voltage;
  final String? label;
  final double iconSize;
  final double fontSize;

  const BatteryIndicator({
    super.key,
    required this.voltage,
    this.label,
    this.iconSize = 14,
    this.fontSize = 11,
  });

  @override
  Widget build(BuildContext context) {
    final color = AppColors.batteryLevel(voltage);
    final v = voltage;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.battery_full, color: color, size: iconSize),
        const SizedBox(width: 2),
        Text(
          label != null
              ? '$label ${v?.toStringAsFixed(1) ?? "—"}V'
              : '${v?.toStringAsFixed(1) ?? "—"}V',
          style: TextStyle(fontSize: fontSize, color: color),
        ),
      ],
    );
  }
}

/// REC chip with red dot + elapsed timer for capture screen.
class RecChip extends StatelessWidget {
  final Duration elapsed;

  const RecChip({super.key, required this.elapsed});

  @override
  Widget build(BuildContext context) {
    return shad.DestructiveBadge(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.fiber_manual_record, color: Colors.red.shade300, size: 10),
          const SizedBox(width: 4),
          Text(
            '${elapsed.inMinutes.toString().padLeft(2, '0')}:'
            '${(elapsed.inSeconds % 60).toString().padLeft(2, '0')}',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

/// Side badge (L/R) for BLE assignment status.
class SideBadge extends StatelessWidget {
  final String label;
  final bool isConnected;
  final bool isLeft;

  const SideBadge({
    super.key,
    required this.label,
    required this.isConnected,
    required this.isLeft,
  });

  @override
  Widget build(BuildContext context) {
    final status = isConnected ? ' ✓' : ' …';
    final badge = isLeft
        ? shad.PrimaryBadge(child: Text('$label$status'))
        : shad.SecondaryBadge(child: Text('$label$status'));
    return badge;
  }
}
