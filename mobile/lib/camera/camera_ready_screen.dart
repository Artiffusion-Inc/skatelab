import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../i18n/strings.g.dart';
import '../../theme/app_theme.dart';
import '../../widgets/battery_indicator.dart';
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
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(
                  Icons.videocam_off,
                  size: 64,
                  color: AppColors.muted,
                ),
                const SizedBox(height: 16),
                Text(
                  _error ?? t.camera.unavailable,
                  style: Theme.of(context).textTheme.bodyMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                shad.PrimaryButton(
                  onPressed: _initCamera,
                  leading: const Icon(Icons.refresh),
                  child: Text(t.camera.retry),
                ),
              ],
            ),
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
                  color: AppColors.overlayBarBg,
                  child: Row(
                    children: [
                      shad.GhostButton(
                        onPressed: () => recorder.toggleGrid(),
                        size: shad.ButtonSize.small,
                        child: Icon(
                          recorder.showGrid ? Icons.grid_on : Icons.grid_off,
                          color: recorder.showGrid
                              ? AppColors.leftSide
                              : Colors.white,
                          size: 22,
                        ),
                      ),
                      shad.GhostButton(
                        onPressed: () => _showSettings(context),
                        size: shad.ButtonSize.small,
                        child: const Icon(
                          Icons.settings,
                          color: Colors.white,
                          size: 22,
                        ),
                      ),
                      const Spacer(),
                      Consumer<BleManager>(
                        builder: (ctx, ble, _) => Row(
                          children: [
                            if (ble.leftDevice != null) ...[
                              BatteryIndicator(
                                label: 'L',
                                voltage:
                                    ble.batteryLevels[ble
                                        .leftDevice!
                                        .device
                                        .remoteId
                                        .str],
                                iconSize: 14,
                                fontSize: 11,
                              ),
                              const SizedBox(width: 6),
                            ],
                            if (ble.rightDevice != null) ...[
                              BatteryIndicator(
                                label: 'R',
                                voltage:
                                    ble.batteryLevels[ble
                                        .rightDevice!
                                        .device
                                        .remoteId
                                        .str],
                                iconSize: 14,
                                fontSize: 11,
                              ),
                            ],
                          ],
                        ),
                      ),
                      shad.GhostButton(
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => const MetricsScreen(),
                            ),
                          );
                        },
                        size: shad.ButtonSize.small,
                        child: const Icon(
                          Icons.show_chart,
                          color: Colors.white,
                          size: 22,
                        ),
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
                          color: AppColors.overlayBg,
                          child: Wrap(
                            spacing: 8,
                            children: [
                              if (ble.leftDevice != null)
                                SideBadge(
                                  label: t.ble.left,
                                  isConnected:
                                      ble.leftDevice!.isConnected.value,
                                  isLeft: true,
                                ),
                              if (ble.rightDevice != null)
                                SideBadge(
                                  label: t.ble.right,
                                  isConnected:
                                      ble.rightDevice!.isConnected.value,
                                  isLeft: false,
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
                    shad.GhostButton(
                      onPressed: () => recorder.toggleCamera(),
                      child: const Icon(
                        Icons.flip_camera_ios,
                        color: Colors.white70,
                        size: 28,
                      ),
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
                            color: AppColors.danger,
                          ),
                        ),
                      ),
                    ),
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
    shad.openSheet(
      context: context,
      position: shad.OverlayPosition.bottom,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                t.camera.settingsTitle,
                style: Theme.of(context).textTheme.titleMedium,
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
                    shad.Switch(
                      value: recorder.orientationLocked,
                      onChanged: (v) => recorder.setOrientationLocked(v),
                      trailing: Text(t.camera.orientation),
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
