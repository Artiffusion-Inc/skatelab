import 'dart:io';
import 'dart:isolate';
import 'package:archive/archive.dart';
import 'package:path_provider/path_provider.dart';
import 'package:fixnum/fixnum.dart';
import '../export/protobuf_gen/imu.pb.dart';
import 'manifest_builder.dart';

class Exporter {
  Future<String> export({
    required String videoPath,
    required List<Map<String, dynamic>> leftSamples,
    required List<Map<String, dynamic>> rightSamples,
    required DateTime t0,
    required List<double> leftRef,
    required List<double> rightRef,
    int videoWidth = 1920,
    int videoHeight = 1080,
    int videoFps = 60,
    String? outputDir,
  }) async {
    final dir = await _ensureExportDir(outputDir);
    final basename = _formatBasename(t0);

    final videoFile = File(videoPath);
    final targetVideo = File('${dir.path}/$basename.mp4');
    if (await videoFile.exists()) {
      await videoFile.copy(targetVideo.path);
    }

    final leftPbPath = '${dir.path}/${basename}_left.pb';
    await _writeProtobuf(leftPbPath, leftSamples);

    final rightPbPath = '${dir.path}/${basename}_right.pb';
    await _writeProtobuf(rightPbPath, rightSamples);

    final manifest = ManifestBuilder.build(
      t0: t0,
      durationMs: _computeDuration(leftSamples, rightSamples),
      videoFilename: '$basename.mp4',
      videoWidth: videoWidth,
      videoHeight: videoHeight,
      videoFps: videoFps,
      leftImuFilename: '${basename}_left.pb',
      rightImuFilename: '${basename}_right.pb',
      leftRef: {'quat_ref': leftRef, 'calibrated_at': t0.toIso8601String()},
      rightRef: {'quat_ref': rightRef, 'calibrated_at': t0.toIso8601String()},
    );
    final manifestPath = '${dir.path}/$basename.json';
    await File(manifestPath).writeAsString(manifest);

    final entries = <MapEntry<String, List<int>>>[
      if (await targetVideo.exists())
        MapEntry('$basename.mp4', await targetVideo.readAsBytes()),
      MapEntry('${basename}_left.pb', await File(leftPbPath).readAsBytes()),
      MapEntry('${basename}_right.pb', await File(rightPbPath).readAsBytes()),
      MapEntry('$basename.json', await File(manifestPath).readAsBytes()),
    ];

    final zipBytes = await Isolate.run(() => _buildZip(entries));
    final zipPath = '${dir.path}/$basename.zip';
    await File(zipPath).writeAsBytes(zipBytes);
    return zipPath;
  }

  static List<int> _buildZip(List<MapEntry<String, List<int>>> entries) {
    final archive = Archive();
    for (final e in entries) {
      archive.addFile(ArchiveFile(e.key, e.value.length, e.value));
    }
    return ZipEncoder().encode(archive);
  }

  Future<Directory> _ensureExportDir(String? outputDir) async {
    if (outputDir != null) return Directory(outputDir);
    Directory? downloads;
    try {
      downloads = await getDownloadsDirectory();
    } catch (_) {}
    if (downloads == null) {
      try {
        downloads = await getExternalStorageDirectory();
      } catch (_) {}
    }
    downloads ??= await getTemporaryDirectory();
    final dir = Directory('${downloads.path}/EdgeSense');
    await dir.create(recursive: true);
    return dir;
  }

  String _formatBasename(DateTime dt) {
    final y = dt.year;
    final m = dt.month.toString().padLeft(2, '0');
    final d = dt.day.toString().padLeft(2, '0');
    final h = dt.hour.toString().padLeft(2, '0');
    final min = dt.minute.toString().padLeft(2, '0');
    final s = dt.second.toString().padLeft(2, '0');
    return 'capture_$y$m${d}_$h$min$s';
  }

  Future<void> _writeProtobuf(
    String path,
    List<Map<String, dynamic>> samples,
  ) async {
    final stream = IMUStream();
    for (final s in samples) {
      stream.samples.add(
        IMUSample(
          relativeTimestampMs: Int64(s['relative_timestamp_ms'] as int),
          accX: (s['acc_x'] as num?)?.toDouble(),
          accY: (s['acc_y'] as num?)?.toDouble(),
          accZ: (s['acc_z'] as num?)?.toDouble(),
          gyroX: (s['gyro_x'] as num?)?.toDouble(),
          gyroY: (s['gyro_y'] as num?)?.toDouble(),
          gyroZ: (s['gyro_z'] as num?)?.toDouble(),
          quatW: (s['quat_w'] as num?)?.toDouble(),
          quatX: (s['quat_x'] as num?)?.toDouble(),
          quatY: (s['quat_y'] as num?)?.toDouble(),
          quatZ: (s['quat_z'] as num?)?.toDouble(),
        ),
      );
    }
    final bytes = stream.writeToBuffer();
    await File(path).writeAsBytes(bytes);
  }

  int _computeDuration(
    List<Map<String, dynamic>> left,
    List<Map<String, dynamic>> right,
  ) {
    int maxTs = 0;
    for (final s in left) {
      final ts = s['relative_timestamp_ms'] as int? ?? 0;
      if (ts > maxTs) maxTs = ts;
    }
    for (final s in right) {
      final ts = s['relative_timestamp_ms'] as int? ?? 0;
      if (ts > maxTs) maxTs = ts;
    }
    return maxTs;
  }
}
