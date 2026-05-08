import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:edgesense_capture/capture/capture_repository.dart';
import 'package:edgesense_capture/ble/ble_manager.dart';
import 'package:edgesense_capture/camera/recorder.dart';
import 'package:edgesense_capture/ble/wt901_parser.dart';

class MockBleManager extends Mock implements BleManager {}

class MockCameraRecorder extends Mock implements CameraRecorder {}

void main() {
  group('CaptureRepository', () {
    late MockBleManager bleManager;
    late MockCameraRecorder cameraRecorder;
    late CaptureRepository repo;

    setUp(() {
      bleManager = MockBleManager();
      cameraRecorder = MockCameraRecorder();
      repo = CaptureRepository(
        bleManager: bleManager,
        cameraRecorder: cameraRecorder,
      );
    });

    tearDown(() {
      repo.dispose();
    });

    test('start succeeds when not already recording', () async {
      when(() => bleManager.connectAll()).thenAnswer((_) async {});
      when(() => cameraRecorder.startRecording()).thenAnswer((_) async {});
      when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

      await repo.start(
        onLeftEdgeAngle: (_) {},
        onRightEdgeAngle: (_) {},
      );

      verify(() => bleManager.connectAll()).called(1);
      verify(() => cameraRecorder.startRecording()).called(1);
    });

    test('start throws when already recording', () async {
      when(() => bleManager.connectAll()).thenAnswer((_) async {});
      when(() => cameraRecorder.startRecording()).thenAnswer((_) async {});
      when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

      await repo.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});
      expect(
        () => repo.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {}),
        throwsStateError,
      );
    });

    test('stop returns CaptureResult with samples and t0', () async {
      final controller =
          StreamController<(WT901Packet?, WT901Packet?)>.broadcast();

      when(() => bleManager.connectAll()).thenAnswer((_) async {});
      when(() => cameraRecorder.startRecording()).thenAnswer((_) async {});
      when(
        () => bleManager.startStreams(),
      ).thenAnswer((_) => controller.stream);
      when(
        () => cameraRecorder.stopRecording(),
      ).thenAnswer((_) async => XFile('/tmp/video.mp4'));
      when(() => bleManager.disconnectAll()).thenAnswer((_) async {});

      await repo.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});

      controller.add((
        WT901Packet(
          type: WT901PacketType.quaternion,
          quatW: 1.0,
          quatX: 0,
          quatY: 0,
          quatZ: 0,
        ),
        WT901Packet(
          type: WT901PacketType.quaternion,
          quatW: 0.99,
          quatX: 0.01,
          quatY: 0,
          quatZ: 0,
        ),
      ));

      // Allow stream listener microtask to process the event
      await Future.delayed(Duration.zero);

      final result = await repo.stop();

      expect(result.videoPath, equals('/tmp/video.mp4'));
      expect(result.leftSamples.length, equals(1));
      expect(result.rightSamples.length, equals(1));
      expect(result.t0, isA<DateTime>());
    });

    test('buffers are cleared on subsequent start', () async {
      final controller =
          StreamController<(WT901Packet?, WT901Packet?)>.broadcast();

      when(() => bleManager.connectAll()).thenAnswer((_) async {});
      when(() => cameraRecorder.startRecording()).thenAnswer((_) async {});
      when(
        () => bleManager.startStreams(),
      ).thenAnswer((_) => controller.stream);
      when(
        () => cameraRecorder.stopRecording(),
      ).thenAnswer((_) async => XFile('/tmp/video.mp4'));
      when(() => bleManager.disconnectAll()).thenAnswer((_) async {});

      // First capture
      await repo.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});
      controller.add((
        WT901Packet(type: WT901PacketType.quaternion, quatW: 1.0),
        null,
      ));
      await repo.stop();

      // Second capture — buffers should be empty initially
      final controller2 =
          StreamController<(WT901Packet?, WT901Packet?)>.broadcast();
      when(
        () => bleManager.startStreams(),
      ).thenAnswer((_) => controller2.stream);
      when(
        () => cameraRecorder.stopRecording(),
      ).thenAnswer((_) async => XFile('/tmp/video2.mp4'));

      await repo.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});
      expect(repo.leftSampleCount, equals(0));
      expect(repo.rightSampleCount, equals(0));

      controller2.add((null, null));
      await repo.stop();
    });
  });
}