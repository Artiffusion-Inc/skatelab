import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../i18n/strings.g.dart';
import '../ble/ble_manager.dart';
import '../capture/capture_provider.dart';
import '../capture/capture_state.dart';
import '../calibration/calibration_service.dart';
import '../camera/recorder.dart';
import 'package:share_plus/share_plus.dart';
import '../export/exporter.dart';
import '../overlay/edge_overlay.dart';

class CapturingScreen extends StatefulWidget {
  final void Function(String? exportPath) onComplete;
  const CapturingScreen({super.key, required this.onComplete});

  @override
  State<CapturingScreen> createState() => _CapturingScreenState();
}

class _CapturingScreenState extends State<CapturingScreen> {
  double _leftAngle = 0;
  double _rightAngle = 0;
  bool _leftActive = false;
  bool _rightActive = false;
  Duration _elapsed = Duration.zero;
  bool _stopping = false;
  Timer? _elapsedTimer;
  Timer? _leftTimeout;
  Timer? _rightTimeout;

  @override
  void initState() {
    super.initState();
    _startCapture();
  }

  @override
  void dispose() {
    _elapsedTimer?.cancel();
    _leftTimeout?.cancel();
    _rightTimeout?.cancel();
    super.dispose();
  }

  Future<void> _startCapture() async {
    final captureProvider = context.read<CaptureProvider>();

    await captureProvider.start(
      onLeftEdgeAngle: (a) {
        setState(() {
          _leftAngle = a;
          _leftActive = true;
        });
        _leftTimeout?.cancel();
        _leftTimeout = Timer(const Duration(milliseconds: 100), () {
          if (mounted) setState(() => _leftActive = false);
        });
      },
      onRightEdgeAngle: (a) {
        setState(() {
          _rightAngle = a;
          _rightActive = true;
        });
        _rightTimeout?.cancel();
        _rightTimeout = Timer(const Duration(milliseconds: 100), () {
          if (mounted) setState(() => _rightActive = false);
        });
      },
    );

    if (captureProvider.status == CaptureStatus.error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(captureProvider.lastError ?? 'Capture failed')),
        );
      }
      widget.onComplete(null);
      return;
    }

    final start = captureProvider.startTime;
    if (start != null) {
      _elapsedTimer = Timer.periodic(const Duration(milliseconds: 200), (_) {
        if (mounted && captureProvider.status == CaptureStatus.recording) {
          setState(() => _elapsed = DateTime.now().difference(start));
        }
      });
    }
  }

  Future<void> _stopCapture() async {
    if (_stopping) return;
    setState(() => _stopping = true);
    _elapsedTimer?.cancel();

    final captureProvider = context.read<CaptureProvider>();
    final calibration = context.read<CalibrationService>();

    try {
      final result = await captureProvider.stop();
      if (result == null) {
        if (mounted) widget.onComplete(null);
        return;
      }

      final leftRef = calibration.leftRef ?? [1.0, 0.0, 0.0, 0.0];
      final rightRef = calibration.rightRef ?? [1.0, 0.0, 0.0, 0.0];

      final exportPath = await Exporter().export(
        videoPath: result.videoPath,
        leftSamples: result.leftSamples,
        rightSamples: result.rightSamples,
        t0: result.t0,
        leftRef: leftRef,
        rightRef: rightRef,
      );
      if (!mounted) return;
      final t = Translations.of(context);
      await Share.shareXFiles([XFile(exportPath)], text: t.capture.shareText);
      if (mounted) widget.onComplete(exportPath);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString())),
        );
        widget.onComplete(null);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    final recorder = context.watch<CameraRecorder>();
    final ble = context.watch<BleManager>();

    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          // Fullscreen camera preview
          if (recorder.isInitialized && recorder.controller != null)
            Positioned.fill(
              child: ClipRect(
                child: OverflowBox(
                  maxWidth: double.infinity,
                  maxHeight: double.infinity,
                  alignment: Alignment.center,
                  child: FittedBox(
                    fit: BoxFit.cover,
                    child: SizedBox(
                      width: recorder.controller!.value.previewSize!.height,
                      height: recorder.controller!.value.previewSize!.width,
                      child: CameraPreview(recorder.controller!),
                    ),
                  ),
                ),
              ),
            )
          else
            const SizedBox.expand(),
          // Grid overlay
          if (recorder.showGrid)
            Positioned.fill(
              child: EdgeOverlay(
                leftAngle: _leftAngle,
                rightAngle: _rightAngle,
                leftActive: _leftActive,
                rightActive: _rightActive,
              ),
            ),
          // Top bar
          SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  color: Colors.black54,
                  child: Row(
                    children: [
                      // REC chip
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.red.shade900,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              Icons.fiber_manual_record,
                              color: Colors.red.shade300,
                              size: 12,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              '${_elapsed.inMinutes.toString().padLeft(2, '0')}:${(_elapsed.inSeconds % 60).toString().padLeft(2, '0')}',
                              style: const TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Spacer(),
                      // Battery levels
                      if (ble.leftDevice != null) ...[
                        _BatteryChip(
                          label: 'L',
                          voltage:
                              ble.batteryLevels[ble
                                  .leftDevice!
                                  .device
                                  .remoteId
                                  .str],
                        ),
                        const SizedBox(width: 6),
                      ],
                      if (ble.rightDevice != null) ...[
                        _BatteryChip(
                          label: 'R',
                          voltage:
                              ble.batteryLevels[ble
                                  .rightDevice!
                                  .device
                                  .remoteId
                                  .str],
                        ),
                      ],
                      const SizedBox(width: 6),
                      // Sample counts
                      Text(
                        'L:${context.select<CaptureProvider, int>((c) => c.leftSampleCount)}  '
                        'R:${context.select<CaptureProvider, int>((c) => c.rightSampleCount)}',
                        style: const TextStyle(
                          fontSize: 11,
                          color: Colors.white70,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      floatingActionButton: shad.DestructiveButton(
        onPressed: _stopping ? null : _stopCapture,
        leading: _stopping
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.stop),
        child: Text(_stopping ? t.capture.saving : t.capture.stop),
      ),
    );
  }
}

class _BatteryChip extends StatelessWidget {
  final String label;
  final double? voltage;

  const _BatteryChip({required this.label, this.voltage});

  @override
  Widget build(BuildContext context) {
    final v = voltage;
    final color = v == null
        ? Colors.grey
        : v > 3.7
        ? Colors.green
        : v > 3.5
        ? Colors.orange
        : Colors.red;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.battery_full, color: color, size: 12),
        const SizedBox(width: 2),
        Text(
          '$label ${v?.toStringAsFixed(1) ?? "—"}V',
          style: TextStyle(fontSize: 10, color: color),
        ),
      ],
    );
  }
}
