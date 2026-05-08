import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'camera_factory.dart';

class CameraRecorder extends ChangeNotifier {
  final CameraFactory _factory;

  CameraRecorder({CameraFactory? factory})
    : _factory = factory ?? SystemCameraFactory();

  CameraController? _controller;
  CameraLensDirection _lensDirection = CameraLensDirection.back;
  ResolutionPreset _resolution = ResolutionPreset.high;
  bool _showGrid = false;
  bool _orientationLocked = false;

  bool get isInitialized => _controller?.value.isInitialized ?? false;
  bool get showGrid => _showGrid;
  bool get orientationLocked => _orientationLocked;
  ResolutionPreset get resolution => _resolution;
  CameraController? get controller => _controller;

  bool _initializing = false;

  Future<void> initialize(List<CameraDescription> cameras) async {
    if (cameras.isEmpty) {
      _controller = null;
      return;
    }
    if (_initializing) return;
    _initializing = true;
    _controller?.dispose();
    _controller = null;
    try {
      final ctrl = _factory.createController(
        cameras.firstWhere(
          (c) => c.lensDirection == _lensDirection,
          orElse: () => cameras.first,
        ),
        _resolution,
        enableAudio: false,
        fps: 60,
      );
      await ctrl.initialize();
      if (_orientationLocked) {
        await SystemChrome.setPreferredOrientations([
          DeviceOrientation.portraitUp,
        ]);
      }
      _controller = ctrl;
    } catch (_) {
      _controller?.dispose();
      _controller = null;
      rethrow;
    } finally {
      _initializing = false;
      notifyListeners();
    }
  }

  Future<void> toggleCamera() async {
    _lensDirection = _lensDirection == CameraLensDirection.back
        ? CameraLensDirection.front
        : CameraLensDirection.back;
    final cameras = await _factory.getCameras();
    await initialize(cameras);
  }

  Future<void> setResolution(ResolutionPreset r) async {
    _resolution = r;
    final cameras = await _factory.getCameras();
    await initialize(cameras);
  }

  Future<void> setOrientationLocked(bool locked) async {
    _orientationLocked = locked;
    if (locked) {
      await SystemChrome.setPreferredOrientations([
        DeviceOrientation.portraitUp,
      ]);
    } else {
      await SystemChrome.setPreferredOrientations([]);
    }
    notifyListeners();
  }

  void toggleGrid() {
    _showGrid = !_showGrid;
    notifyListeners();
  }

  Future<void> startRecording() async {
    if (_controller == null || !isInitialized) {
      throw StateError('Camera not initialized');
    }
    await _controller!.startVideoRecording();
  }

  Future<XFile> stopRecording() async {
    if (_controller == null || !isInitialized) {
      throw StateError('Camera not initialized');
    }
    return await _controller!.stopVideoRecording();
  }

  @override
  void dispose() {
    _controller?.dispose();
    _controller = null;
    super.dispose();
  }
}
