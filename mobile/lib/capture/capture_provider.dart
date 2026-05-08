import 'package:flutter/foundation.dart';

import '../ble/ble_manager.dart';
import '../camera/recorder.dart';
import 'capture_repository.dart';
import 'capture_state.dart';

class CaptureProvider extends ChangeNotifier {
  final CaptureRepository _repo;

  CaptureStatus status = CaptureStatus.idle;
  String? lastError;
  DateTime? get startTime => _repo.startTime;
  int get leftSampleCount => _repo.leftSampleCount;
  int get rightSampleCount => _repo.rightSampleCount;

  CaptureProvider({
    required BleManager bleManager,
    required CameraRecorder cameraRecorder,
  }) : _repo = CaptureRepository(
         bleManager: bleManager,
         cameraRecorder: cameraRecorder,
       );

  Future<void> start({
    required void Function(double edgeAngle) onLeftEdgeAngle,
    required void Function(double edgeAngle) onRightEdgeAngle,
  }) async {
    if (status == CaptureStatus.recording) return;

    status = CaptureStatus.initializing;
    lastError = null;
    notifyListeners();

    try {
      await _repo.start(
        onLeftEdgeAngle: onLeftEdgeAngle,
        onRightEdgeAngle: onRightEdgeAngle,
      );
      status = CaptureStatus.recording;
    } catch (e) {
      status = CaptureStatus.error;
      lastError = e.toString();
    }
    notifyListeners();
  }

  Future<CaptureResult?> stop() async {
    if (status != CaptureStatus.recording) return null;

    status = CaptureStatus.stopping;
    notifyListeners();

    try {
      final result = await _repo.stop();
      status = CaptureStatus.idle;
      notifyListeners();
      return result;
    } catch (e) {
      status = CaptureStatus.error;
      lastError = e.toString();
      notifyListeners();
      return null;
    }
  }

  @override
  void dispose() {
    _repo.dispose();
    super.dispose();
  }
}
