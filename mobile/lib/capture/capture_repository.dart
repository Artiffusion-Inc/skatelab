import 'dart:async';
import 'dart:math' as math;

import '../ble/ble_manager.dart';
import '../ble/wt901_parser.dart';
import '../camera/recorder.dart';
import 'capture_state.dart';

class CaptureRepository {
  final BleManager _bleManager;
  final CameraRecorder _cameraRecorder;

  final List<Map<String, dynamic>> _leftBuffer = [];
  final List<Map<String, dynamic>> _rightBuffer = [];
  StreamSubscription? _streamSubscription;
  DateTime? _t0;

  CaptureRepository({
    required BleManager bleManager,
    required CameraRecorder cameraRecorder,
  }) : _bleManager = bleManager,
       _cameraRecorder = cameraRecorder;

  DateTime? get startTime => _t0;
  int get leftSampleCount => _leftBuffer.length;
  int get rightSampleCount => _rightBuffer.length;

  /// Starts capture. Throws if already recording.
  Future<void> start({
    required void Function(double edgeAngle) onLeftEdgeAngle,
    required void Function(double edgeAngle) onRightEdgeAngle,
  }) async {
    if (_streamSubscription != null) {
      throw StateError('Capture already in progress');
    }

    _leftBuffer.clear();
    _rightBuffer.clear();

    await _bleManager.connectAll();
    await _cameraRecorder.startRecording();

    final stopwatch = Stopwatch()..start();
    _t0 = DateTime.now();

    _streamSubscription = _bleManager.startStreams().listen((pair) {
      final relativeMs = stopwatch.elapsed.inMilliseconds;

      final left = pair.$1;
      if (left != null) {
        _leftBuffer.add(_toMap(left, relativeMs));
        if (left.quatW != null) {
          onLeftEdgeAngle(_computeEdgeAngle(left));
        }
      }

      final right = pair.$2;
      if (right != null) {
        _rightBuffer.add(_toMap(right, relativeMs));
        if (right.quatW != null) {
          onRightEdgeAngle(_computeEdgeAngle(right));
        }
      }
    });
  }

  Future<CaptureResult> stop() async {
    await _streamSubscription?.cancel();
    _streamSubscription = null;

    final videoFile = await _cameraRecorder.stopRecording();
    await _bleManager.disconnectAll();

    if (_t0 == null) {
      throw StateError('No capture in progress');
    }

    return CaptureResult(
      videoPath: videoFile.path,
      leftSamples: List.from(_leftBuffer),
      rightSamples: List.from(_rightBuffer),
      t0: _t0!,
    );
  }

  void dispose() {
    _streamSubscription?.cancel();
  }

  Map<String, dynamic> _toMap(WT901Packet packet, int relativeMs) {
    return {
      'relative_timestamp_ms': relativeMs,
      'acc_x': packet.accX,
      'acc_y': packet.accY,
      'acc_z': packet.accZ,
      'gyro_x': packet.gyroX,
      'gyro_y': packet.gyroY,
      'gyro_z': packet.gyroZ,
      'quat_w': packet.quatW,
      'quat_x': packet.quatX,
      'quat_y': packet.quatY,
      'quat_z': packet.quatZ,
    };
  }

  double _computeEdgeAngle(WT901Packet p) {
    final qx = p.quatX ?? 0;
    final qy = p.quatY ?? 0;
    final qz = p.quatZ ?? 0;
    final qw = p.quatW ?? 0;
    final roll = math.atan2(
      2.0 * (qw * qx + qy * qz),
      1.0 - 2.0 * (qx * qx + qy * qy),
    );
    return 180.0 / math.pi * roll;
  }
}
