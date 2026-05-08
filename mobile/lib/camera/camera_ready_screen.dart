import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../i18n/strings.g.dart';
import '../ble/ble_manager.dart';
import '../metrics/metrics_screen.dart';
import 'grid_overlay.dart';
import 'recorder.dart';

class CameraReadyScreen extends StatefulWidget {
  final VoidCallback onStartCapture;
  const CameraReadyScreen({super.key, required this.onStartCapture});

  @override
  State<CameraReadyScreen> createState() => _CameraReadyScreenState();
}

class _CameraReadyScreenState extends State<CameraReadyScreen> {
  bool _initializing = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    setState(() {
      _initializing = true;
      _error = null;
    });
    try {
      final cameras = await availableCameras();
      if (!mounted) return;
      final recorder = context.read<CameraRecorder>();
      await recorder.initialize(cameras);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _initializing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    final recorder = context.watch<CameraRecorder>();

    if (_initializing) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (_error != null || !recorder.isInitialized) {
      return Scaffold(
        appBar: AppBar(title: Text(t.camera.title)),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.videocam_off, size: 64, color: Colors.white54),
              const SizedBox(height: 16),
              Text(
                _error ?? t.camera.unavailable,
                style: const TextStyle(fontSize: 16),
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _initCamera,
                icon: const Icon(Icons.refresh),
                label: Text(t.camera.retry),
              ),
            ],
          ),
        ),
      );
    }

    final controller = recorder.controller!;
    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          // Camera preview — fullscreen cover
          if (controller.value.isInitialized)
            Positioned.fill(
              child: ClipRect(
                child: OverflowBox(
                  maxWidth: double.infinity,
                  maxHeight: double.infinity,
                  alignment: Alignment.center,
                  child: FittedBox(
                    fit: BoxFit.cover,
                    child: SizedBox(
                      width: controller.value.previewSize!.height,
                      height: controller.value.previewSize!.width,
                      child: CameraPreview(controller),
                    ),
                  ),
                ),
              ),
            )
          else
            const SizedBox.expand(),
          // Grid overlay
          if (recorder.showGrid) const Positioned.fill(child: GridOverlay()),
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
                      // Grid toggle
                      IconButton(
                        icon: Icon(
                          recorder.showGrid ? Icons.grid_on : Icons.grid_off,
                          color: recorder.showGrid ? Colors.blue : Colors.white,
                          size: 22,
                        ),
                        tooltip: t.camera.grid,
                        onPressed: () => recorder.toggleGrid(),
                      ),
                      // Settings
                      IconButton(
                        icon: const Icon(
                          Icons.settings,
                          color: Colors.white,
                          size: 22,
                        ),
                        tooltip: t.camera.settings,
                        onPressed: () => _showSettings(context),
                      ),
                      const Spacer(),
                      // Battery levels
                      Consumer<BleManager>(
                        builder: (ctx, ble, _) => Row(
                          children: [
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
                          ],
                        ),
                      ),
                      // Metrics button
                      IconButton(
                        icon: const Icon(
                          Icons.show_chart,
                          color: Colors.white,
                          size: 22,
                        ),
                        tooltip: t.camera.sensors,
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => const MetricsScreen(),
                            ),
                          );
                        },
                      ),
                    ],
                  ),
                ),
                // IMU status chips
                Consumer<BleManager>(
                  builder: (ctx, ble, _) =>
                      ble.leftDevice != null || ble.rightDevice != null
                      ? Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 4,
                          ),
                          color: Colors.black38,
                          child: Wrap(
                            spacing: 8,
                            children: [
                              if (ble.leftDevice != null)
                                shad.PrimaryBadge(
                                  child: Text(
                                    '${t.ble.left} ${ble.leftDevice!.isConnected.value ? "✓" : "…"}',
                                  ),
                                ),
                              if (ble.rightDevice != null)
                                shad.PrimaryBadge(
                                  child: Text(
                                    '${t.ble.right} ${ble.rightDevice!.isConnected.value ? "✓" : "…"}',
                                  ),
                                ),
                            ],
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
          // Bottom controls
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 16,
                ),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.transparent,
                      Colors.black.withValues(alpha: 0.7),
                    ],
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    // Flip camera
                    IconButton(
                      icon: const Icon(
                        Icons.flip_camera_ios,
                        color: Colors.white70,
                        size: 28,
                      ),
                      onPressed: () => recorder.toggleCamera(),
                    ),
                    // Record button
                    GestureDetector(
                      onTap: widget.onStartCapture,
                      child: Container(
                        width: 72,
                        height: 72,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 4),
                        ),
                        child: Container(
                          margin: const EdgeInsets.all(4),
                          decoration: const BoxDecoration(
                            shape: BoxShape.circle,
                            color: Colors.red,
                          ),
                        ),
                      ),
                    ),
                    // Placeholder for future feature
                    const SizedBox(width: 28, height: 28),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _showSettings(BuildContext context) {
    final t = Translations.of(context);
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                t.camera.settingsTitle,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              Consumer<CameraRecorder>(
                builder: (context, recorder, _) => Column(
                  children: [
                    ListTile(
                      leading: const Icon(Icons.hd),
                      title: Text(t.camera.resolution),
                      trailing: DropdownButton<ResolutionPreset>(
                        value: recorder.resolution,
                        underline: const SizedBox.shrink(),
                        items: ResolutionPreset.values.map((r) {
                          final label =
                              {
                                ResolutionPreset.low: t.camera.resolutions.low,
                                ResolutionPreset.medium:
                                    t.camera.resolutions.medium,
                                ResolutionPreset.high:
                                    t.camera.resolutions.high,
                                ResolutionPreset.veryHigh:
                                    t.camera.resolutions.veryHigh,
                                ResolutionPreset.ultraHigh:
                                    t.camera.resolutions.ultraHigh,
                                ResolutionPreset.max: t.camera.resolutions.max,
                              }[r] ??
                              r.name;
                          return DropdownMenuItem(value: r, child: Text(label));
                        }).toList(),
                        onChanged: (v) {
                          if (v != null) recorder.setResolution(v);
                        },
                      ),
                    ),
                    SwitchListTile(
                      secondary: const Icon(Icons.screen_lock_portrait),
                      title: Text(t.camera.orientation),
                      subtitle: Text(t.camera.portrait),
                      value: recorder.orientationLocked,
                      onChanged: (v) => recorder.setOrientationLocked(v),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
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
        Icon(Icons.battery_full, color: color, size: 14),
        const SizedBox(width: 2),
        Text(
          '$label ${v?.toStringAsFixed(1) ?? "—"}V',
          style: TextStyle(fontSize: 11, color: color),
        ),
      ],
    );
  }
}
