import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:edgesense_capture/capture/capture_provider.dart';
import 'package:edgesense_capture/capture/capture_state.dart';
import 'package:edgesense_capture/ble/ble_manager.dart';
import 'package:edgesense_capture/camera/recorder.dart';

class MockBleManager extends Mock implements BleManager {}

class MockCameraRecorder extends Mock implements CameraRecorder {}

void main() {
  group('CaptureProvider', () {
    late MockBleManager bleManager;
    late MockCameraRecorder cameraRecorder;
    late CaptureProvider provider;

    setUp(() {
      bleManager = MockBleManager();
      cameraRecorder = MockCameraRecorder();
      provider = CaptureProvider(
        bleManager: bleManager,
        cameraRecorder: cameraRecorder,
      );

      // Default stubs for common calls
      when(() => bleManager.connectAll()).thenAnswer((_) async {});
      when(() => bleManager.disconnectAll()).thenAnswer((_) async {});
      when(() => cameraRecorder.startRecording()).thenAnswer((_) async {});
      when(
        () => cameraRecorder.stopRecording(),
      ).thenAnswer((_) async => XFile('/tmp/video.mp4'));
    });

    tearDown(() {
      provider.dispose();
    });

    test('initial status is idle', () {
      expect(provider.status, equals(CaptureStatus.idle));
    });

    test('start transitions status to recording', () async {
      when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

      await provider.start(
        onLeftEdgeAngle: (_) {},
        onRightEdgeAngle: (_) {},
      );

      expect(provider.status, equals(CaptureStatus.recording));
    });

    test(
      'start while already recording keeps status recording and does not reinitialize',
      () async {
        when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

        await provider.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});
        await provider.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});

        expect(provider.status, equals(CaptureStatus.recording));
        verify(() => bleManager.connectAll()).called(1); // Only once
      },
    );

    test('stop transitions status back to idle', () async {
      when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

      await provider.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});
      expect(provider.status, equals(CaptureStatus.recording));

      final result = await provider.stop();

      expect(result, isA<CaptureResult>());
      expect(provider.status, equals(CaptureStatus.idle));
    });

    test('status transitions through initializing → recording', () async {
      final statuses = <CaptureStatus>[];
      provider.addListener(() => statuses.add(provider.status));

      when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

      await provider.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});

      expect(statuses, contains(CaptureStatus.initializing));
      expect(statuses, contains(CaptureStatus.recording));
    });

    test('sample counts reflect repository state', () async {
      when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

      await provider.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});

      expect(provider.leftSampleCount, equals(0));
      expect(provider.rightSampleCount, equals(0));

      await provider.stop();
    });

    test('startTime is set after successful start', () async {
      when(() => bleManager.startStreams()).thenAnswer((_) => Stream.empty());

      expect(provider.startTime, isNull);

      await provider.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});

      expect(provider.startTime, isA<DateTime>());
    });

    test('start sets error status on failure', () async {
      when(() => bleManager.connectAll()).thenThrow(Exception('BLE failed'));

      await provider.start(onLeftEdgeAngle: (_) {}, onRightEdgeAngle: (_) {});

      expect(provider.status, equals(CaptureStatus.error));
      expect(provider.lastError, isNotNull);
    });

    test('stop returns null when not recording', () async {
      final result = await provider.stop();
      expect(result, isNull);
    });
  });
}