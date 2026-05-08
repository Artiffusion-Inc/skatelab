import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'wt901_parser.dart';
import 'imu_device.dart';
import 'ble_platform.dart';
import 'ble_platform_fbp.dart';

enum BleScanError { bluetoothOff, locationRequired, unknown }

class BleManager extends ChangeNotifier {
  List<ScanResult> scanResults = [];
  List<ScanResult> get namedScanResults =>
      scanResults.where((r) => r.device.platformName.isNotEmpty).toList();
  IMUDevice? leftDevice;
  IMUDevice? rightDevice;
  bool isScanning = false;
  BleScanError? scanError;
  String? scanErrorMessage;
  bool locationPermissionGranted = false;

  final Map<String, double> batteryLevels = {};

  final BlePlatform _platform;
  StreamSubscription? _scanSubscription;
  StreamSubscription? _adapterSubscription;

  BleManager({BlePlatform? platform})
    : _platform = platform ?? BlePlatformFbp() {
    _adapterSubscription = _platform.adapterState.listen((state) {
      if (state == BluetoothAdapterState.off) {
        stopScan();
      }
      notifyListeners();
    });
  }

  bool get isBluetoothOn =>
      _platform.adapterStateNow == BluetoothAdapterState.on;

  bool get canProceed =>
      (leftDevice?.isConnected.value ?? false) ||
      (rightDevice?.isConnected.value ?? false);

  Future<bool> checkLocationPermission() async {
    locationPermissionGranted = await _platform.locationGranted;
    notifyListeners();
    return locationPermissionGranted;
  }

  Future<bool> checkBluetoothPermissions() async =>
      await _platform.bluetoothScanGranted &&
      await _platform.bluetoothConnectGranted;

  DateTime? _lastScanStop;

  Future<void> startScan() async {
    if (isScanning) return;
    if (!isBluetoothOn) {
      scanError = BleScanError.bluetoothOff;
      scanErrorMessage = null;
      notifyListeners();
      return;
    }
    if (!await checkLocationPermission()) {
      scanError = BleScanError.locationRequired;
      scanErrorMessage = null;
      notifyListeners();
      return;
    }

    scanError = null;
    scanErrorMessage = null;

    // Throttle: Android blocks scan if restarted within ~5s
    if (_lastScanStop != null) {
      final elapsed = DateTime.now().difference(_lastScanStop!);
      if (elapsed.inSeconds < 6) {
        await Future.delayed(Duration(seconds: 6 - elapsed.inSeconds));
      }
    }

    // Ensure previous scan fully stopped
    await _platform.stopScan();
    await _scanSubscription?.cancel();
    _scanSubscription = null;
    scanResults = [];
    notifyListeners();

    isScanning = true;
    notifyListeners();

    _scanSubscription = _platform.scanResults.listen((results) {
      scanResults = results;
      notifyListeners();
    });

    try {
      await _platform.startScan(
        timeout: const Duration(seconds: 10),
        androidScanMode: AndroidScanMode.lowLatency,
      );
    } catch (e) {
      scanError = BleScanError.unknown;
      scanErrorMessage = e.toString();
    }

    isScanning = false;
    _lastScanStop = DateTime.now();
    notifyListeners();
  }

  Future<void> stopScan() async {
    await _scanSubscription?.cancel();
    _scanSubscription = null;
    await _platform.stopScan();
    isScanning = false;
    _lastScanStop = DateTime.now();
    notifyListeners();
  }

  void assignDevice(String side, BluetoothDevice device) {
    final imu = IMUDevice(
      device: device,
      side: side,
      onBattery: (v) {
        batteryLevels[device.remoteId.str] = v;
        notifyListeners();
      },
    );

    if (side == 'left') {
      leftDevice?.isConnected.removeListener(notifyListeners);
      leftDevice?.dispose();
      leftDevice = imu;
    } else {
      rightDevice?.isConnected.removeListener(notifyListeners);
      rightDevice?.dispose();
      rightDevice = imu;
    }
    imu.isConnected.addListener(notifyListeners);
    _connectDevice(imu);
    notifyListeners();
  }

  Future<void> _connectDevice(IMUDevice imu) async {
    try {
      await imu.connect();
    } catch (e) {
      scanError = BleScanError.unknown;
      scanErrorMessage = 'Connection failed: $e';
      notifyListeners();
    }
  }

  void unassignDevice(String side) {
    if (side == 'left') {
      leftDevice?.dispose();
      leftDevice = null;
    } else {
      rightDevice?.dispose();
      rightDevice = null;
    }
    notifyListeners();
  }

  Future<void> connectAll() async {
    await Future.wait([
      if (leftDevice != null && !leftDevice!.isConnected.value)
        leftDevice!.connect(),
      if (rightDevice != null && !rightDevice!.isConnected.value)
        rightDevice!.connect(),
    ]);
  }

  Future<void> disconnectAll() async {
    await Future.wait([
      if (leftDevice != null) leftDevice!.disconnect(),
      if (rightDevice != null) rightDevice!.disconnect(),
    ]);
  }

  Stream<(WT901Packet?, WT901Packet?)> startStreams() {
    final controller =
        StreamController<(WT901Packet?, WT901Packet?)>.broadcast();
    WT901Packet? lastLeft, lastRight;
    StreamSubscription? leftSub, rightSub;
    StreamSubscription? leftConnSub, rightConnSub;
    Timer? timer;

    void emit() {
      if (!controller.isClosed) controller.add((lastLeft, lastRight));
    }

    void onDeviceDisconnected() {
      if (!controller.isClosed) controller.close();
    }

    if (leftDevice != null && leftDevice!.isConnected.value) {
      leftSub = leftDevice!.startNotifications().listen((p) {
        lastLeft = p;
        emit();
      }, onError: (_) => onDeviceDisconnected());
      leftConnSub = leftDevice!.device.connectionState.listen((state) {
        if (state == BluetoothConnectionState.disconnected) {
          onDeviceDisconnected();
        }
      });
    }
    if (rightDevice != null && rightDevice!.isConnected.value) {
      rightSub = rightDevice!.startNotifications().listen((p) {
        lastRight = p;
        emit();
      }, onError: (_) => onDeviceDisconnected());
      rightConnSub = rightDevice!.device.connectionState.listen((state) {
        if (state == BluetoothConnectionState.disconnected) {
          onDeviceDisconnected();
        }
      });
    }

    timer = Timer.periodic(const Duration(milliseconds: 100), (_) => emit());

    controller.onCancel = () {
      timer?.cancel();
      leftSub?.cancel();
      rightSub?.cancel();
      leftConnSub?.cancel();
      rightConnSub?.cancel();
    };

    return controller.stream;
  }

  @override
  void dispose() {
    _scanSubscription?.cancel();
    _adapterSubscription?.cancel();
    leftDevice?.dispose();
    rightDevice?.dispose();
    super.dispose();
  }
}
