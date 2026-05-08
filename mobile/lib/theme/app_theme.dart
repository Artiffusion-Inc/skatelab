import 'package:flutter/material.dart';

class AppColors {
  // Semantic tokens
  static const seed = Color(0xFF1E88E5);
  static const success = Color(0xFF4CAF50);
  static const warning = Color(0xFFFF9800);
  static const danger = Color(0xFFE53935);
  static const muted = Color(0xFF9E9E9E);

  // Battery levels
  static Color batteryLevel(double? v) => v == null
      ? muted
      : v > 3.7
      ? success
      : v > 3.5
      ? warning
      : danger;

  // Side indicators
  static const leftSide = Color(0xFF42A5F5);
  static const rightSide = Color(0xFFAB47BC);

  // Status bar
  static Color statusBothConnected = Colors.green.shade800;
  static Color statusOneConnected = Colors.orange.shade800;
  static Color statusNone = Colors.grey.shade800;

  // Camera overlay
  static const overlayBg = Color(0x8A000000);
  static const overlayBarBg = Color(0x8C000000);
}

class AppTheme {
  static ThemeData get dark {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.seed,
        brightness: Brightness.dark,
      ),
    );
  }
}
