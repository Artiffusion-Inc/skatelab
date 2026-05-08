import 'package:flutter/material.dart';

class RadialGauge extends StatelessWidget {
  final double value;
  final double min;
  final double max;
  final String label;
  final String unit;

  const RadialGauge({
    super.key,
    required this.value,
    this.min = -2000,
    this.max = 2000,
    required this.label,
    required this.unit,
  });

  @override
  Widget build(BuildContext context) {
    final clamped = value.clamp(min, max);
    final fraction = (clamped - min) / (max - min);
    final cs = Theme.of(context).colorScheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 80,
          height: 80,
          child: CircularProgressIndicator(
            value: fraction,
            strokeWidth: 8,
            backgroundColor: cs.surfaceContainerHighest,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          '${value.toStringAsFixed(1)} $unit',
          style: TextStyle(fontSize: 12, color: cs.onSurface),
        ),
        Text(label, style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant)),
      ],
    );
  }
}
