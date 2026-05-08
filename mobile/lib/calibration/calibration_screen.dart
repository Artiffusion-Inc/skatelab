import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../i18n/strings.g.dart';
import '../../theme/app_theme.dart';
import '../ble/ble_manager.dart';
import 'calibration_service.dart';

class CalibrationScreen extends StatefulWidget {
  final VoidCallback onComplete;
  const CalibrationScreen({super.key, required this.onComplete});

  @override
  State<CalibrationScreen> createState() => _CalibrationScreenState();
}

class _CalibrationScreenState extends State<CalibrationScreen> {
  static const _calibDuration = Duration(seconds: 3);
  bool _running = false;
  bool _done = false;
  double _progress = 0;
  String? _error;
  StreamSubscription? _sub;
  final List<List<double>> _leftQuats = [];
  final List<List<double>> _rightQuats = [];

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<void> _startCalibration() async {
    setState(() {
      _running = true;
      _done = false;
      _error = null;
      _progress = 0;
      _leftQuats.clear();
      _rightQuats.clear();
    });

    final ble = context.read<BleManager>();
    try {
      await ble.connectAll();
    } catch (e) {
      setState(() {
        _running = false;
        _error = '${Translations.of(context).calibration.errorPrefix}: $e';
      });
      return;
    }

    final stream = ble.startStreams();
    final sw = Stopwatch()..start();

    _sub = stream.listen((pair) {
      final left = pair.$1;
      final right = pair.$2;

      if (left != null && left.quatW != null) {
        _leftQuats.add([left.quatW!, left.quatX!, left.quatY!, left.quatZ!]);
      }
      if (right != null && right.quatW != null) {
        _rightQuats.add([
          right.quatW!,
          right.quatX!,
          right.quatY!,
          right.quatZ!,
        ]);
      }

      final elapsed = sw.elapsed;
      if (mounted) {
        setState(() {
          _progress = (elapsed.inMilliseconds / _calibDuration.inMilliseconds)
              .clamp(0.0, 1.0);
        });
      }

      if (elapsed >= _calibDuration) {
        _sub?.cancel();
        _finish();
      }
    });
  }

  void _finish() {
    final calibration = context.read<CalibrationService>();

    if (_leftQuats.isNotEmpty) {
      calibration.leftRef = calibration.calibrate(_leftQuats);
    }
    if (_rightQuats.isNotEmpty) {
      calibration.rightRef = calibration.calibrate(_rightQuats);
    }

    if (mounted) {
      setState(() {
        _running = false;
        _done = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(t.calibration.title)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.straighten, size: 64, color: AppColors.muted),
              const SizedBox(height: 24),
              Text(
                _done
                    ? t.calibration.done
                    : _running
                    ? t.calibration.running
                    : t.calibration.instruction,
                style: Theme.of(context).textTheme.titleMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              if (_running) ...[
                SizedBox(width: 200, child: shad.Progress(progress: _progress)),
                const SizedBox(height: 8),
                Text(
                  '${(_progress * _calibDuration.inSeconds).toStringAsFixed(1)} / ${_calibDuration.inSeconds} ${t.calibration.seconds}',
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
              if (_error != null) ...[
                const SizedBox(height: 16),
                shad.Alert.destructive(title: Text(_error!)),
              ],
              if (_done) ...[
                const SizedBox(height: 16),
                _CalibResult(
                  label: t.calibration.left,
                  ref: context.watch<CalibrationService>().leftRef,
                ),
                const SizedBox(height: 8),
                _CalibResult(
                  label: t.calibration.right,
                  ref: context.watch<CalibrationService>().rightRef,
                ),
                const SizedBox(height: 24),
                shad.PrimaryButton(
                  onPressed: widget.onComplete,
                  leading: const Icon(Icons.arrow_forward),
                  child: Text(t.calibration.startCapture),
                ),
              ],
              if (!_running && !_done) ...[
                const SizedBox(height: 24),
                shad.PrimaryButton(
                  onPressed: _startCalibration,
                  leading: const Icon(Icons.play_arrow),
                  child: Text(t.calibration.calibrate),
                ),
                const SizedBox(height: 12),
                shad.GhostButton(
                  onPressed: widget.onComplete,
                  child: Text(t.calibration.skip),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _CalibResult extends StatelessWidget {
  final String label;
  final List<double>? ref;
  const _CalibResult({required this.label, required this.ref});

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    final r = ref;
    if (r == null) {
      return Text(
        '$label: ${t.calibration.noData}',
        style: const TextStyle(color: AppColors.muted),
      );
    }
    return Text(
      '$label: q=[${r[0].toStringAsFixed(3)}, ${r[1].toStringAsFixed(3)}, ${r[2].toStringAsFixed(3)}, ${r[3].toStringAsFixed(3)}]',
      style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
    );
  }
}
