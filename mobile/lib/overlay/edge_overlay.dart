import 'package:flutter/material.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../i18n/strings.g.dart';
import '../../theme/app_theme.dart';

class EdgeOverlay extends StatelessWidget {
  final double leftAngle;
  final double rightAngle;
  final bool leftActive;
  final bool rightActive;

  const EdgeOverlay({
    super.key,
    required this.leftAngle,
    required this.rightAngle,
    this.leftActive = false,
    this.rightActive = false,
  });

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    final leftStale = !leftActive;
    final rightStale = !rightActive;

    return Positioned(
      top: 40,
      left: 20,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.overlayBg,
          borderRadius: BorderRadius.circular(8),
          border: (leftStale || rightStale)
              ? Border.all(
                  color: AppColors.danger.withValues(alpha: 0.7),
                  width: 2,
                )
              : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (leftStale) ...[
                  shad.Tooltip(
                    tooltip: (_) => Text(t.overlay.staleAlert),
                    child: Icon(
                      Icons.warning_amber,
                      color: AppColors.danger.withValues(alpha: 0.8),
                      size: 16,
                    ),
                  ),
                  const SizedBox(width: 4),
                ],
                Text(
                  '${t.overlay.leftLabel} ${leftAngle.toStringAsFixed(1)}°',
                  style: TextStyle(
                    color: leftStale
                        ? AppColors.danger.withValues(alpha: 0.7)
                        : Colors.white,
                    fontSize: 18,
                    fontWeight: leftStale ? FontWeight.bold : null,
                  ),
                ),
              ],
            ),
            Row(
              children: [
                if (rightStale) ...[
                  shad.Tooltip(
                    tooltip: (_) => Text(t.overlay.staleAlert),
                    child: Icon(
                      Icons.warning_amber,
                      color: AppColors.danger.withValues(alpha: 0.8),
                      size: 16,
                    ),
                  ),
                  const SizedBox(width: 4),
                ],
                Text(
                  '${t.overlay.rightLabel} ${rightAngle.toStringAsFixed(1)}°',
                  style: TextStyle(
                    color: rightStale
                        ? AppColors.danger.withValues(alpha: 0.7)
                        : Colors.white,
                    fontSize: 18,
                    fontWeight: rightStale ? FontWeight.bold : null,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
