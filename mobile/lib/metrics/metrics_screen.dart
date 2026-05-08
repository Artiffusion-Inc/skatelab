import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../i18n/strings.g.dart';
import '../ble/ble_manager.dart';
import '../ble/wt901_parser.dart';
import 'gauge_widget.dart';

class MetricsScreen extends StatefulWidget {
  const MetricsScreen({super.key});

  @override
  State<MetricsScreen> createState() => _MetricsScreenState();
}

class _MetricsScreenState extends State<MetricsScreen> {
  double _gx = 0, _gy = 0, _gz = 0;
  double _ax = 0, _ay = 0, _az = 0;
  double _edgeAngle = 0;
  StreamSubscription? _sub;

  @override
  void initState() {
    super.initState();
    final ble = context.read<BleManager>();
    ble.connectAll();
    _sub = ble.startStreams().listen((pair) {
      if (!mounted) return;
      setState(() {
        final left = pair.$1;
        if (left != null) {
          _gx = left.gyroX ?? _gx;
          _gy = left.gyroY ?? _gy;
          _gz = left.gyroZ ?? _gz;
          _ax = left.accX ?? _ax;
          _ay = left.accY ?? _ay;
          _az = left.accZ ?? _az;
          _edgeAngle = _computeRoll(left);
        }
      });
    });
  }

  double _computeRoll(WT901Packet p) {
    final qx = p.quatX ?? 0,
        qy = p.quatY ?? 0,
        qz = p.quatZ ?? 0,
        qw = p.quatW ?? 0;
    final roll = math.atan2(
      2.0 * (qw * qx + qy * qz),
      1.0 - 2.0 * (qx * qx + qy * qy),
    );
    return 180.0 / math.pi * roll;
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(t.metrics.title)),
      body: Row(
        children: [
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  t.metrics.gyro,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                RadialGauge(value: _gx, label: 'X', unit: '°/s'),
                const SizedBox(height: 8),
                RadialGauge(value: _gy, label: 'Y', unit: '°/s'),
                const SizedBox(height: 8),
                RadialGauge(value: _gz, label: 'Z', unit: '°/s'),
              ],
            ),
          ),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  t.metrics.accel,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                RadialGauge(value: _ax, label: 'X', unit: 'g'),
                const SizedBox(height: 8),
                RadialGauge(value: _ay, label: 'Y', unit: 'g'),
                const SizedBox(height: 8),
                RadialGauge(value: _az, label: 'Z', unit: 'g'),
              ],
            ),
          ),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  t.metrics.edgeAngle,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                RadialGauge(
                  value: _edgeAngle,
                  min: -90,
                  max: 90,
                  label: 'Roll',
                  unit: '°',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
