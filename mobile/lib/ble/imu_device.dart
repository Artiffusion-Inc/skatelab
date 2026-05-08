import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'wt901_parser.dart';

class IMUDevice {
  final BluetoothDevice device;
  final String side;
  final void Function(double voltage)? onBattery;

  final ValueNotifier<bool> isConnected = ValueNotifier<bool>(false);

  StreamSubscription? _notifySubscription;
  StreamSubscription? _connectionSubscription;

  IMUDevice({required this.device, required this.side, this.onBattery}) {
    isConnected.value = device.isConnected;
    _connectionSubscription = device.connectionState.listen((state) {
      final connected = state == BluetoothConnectionState.connected;
      if (isConnected.value != connected) {
        isConnected.value = connected;
      }
    });
  }

  static const _connectTimeout = Duration(seconds: 10);
  static const _disconnectTimeout = Duration(seconds: 5);

  Future<void> connect() async {
    await device.connect(autoConnect: false).timeout(_connectTimeout);
  }

  Future<void> disconnect() async {
    await _notifySubscription?.cancel();
    _notifySubscription = null;
    try {
      await device.disconnect().timeout(_disconnectTimeout);
    } catch (_) {}
  }

  void dispose() {
    _notifySubscription?.cancel();
    _notifySubscription = null;
    _connectionSubscription?.cancel();
    _connectionSubscription = null;
    isConnected.dispose();
  }

  Stream<WT901Packet> startNotifications() async* {
    final services = await device.discoverServices();
    final targetService = services.firstWhere(
      (s) => s.uuid.toString().toLowerCase().contains('ffe0'),
      orElse: () => services.first,
    );
    final characteristic = targetService.characteristics.firstWhere(
      (c) => c.properties.notify,
    );
    await characteristic.setNotifyValue(true);
    _notifySubscription = characteristic.lastValueStream.listen((_) {});
    await for (final event in characteristic.lastValueStream) {
      if (!device.isConnected) break;
      final packet = WT901Parser.parse(event);
      if (packet != null) {
        if (packet.type == WT901PacketType.battery && packet.battery != null) {
          onBattery?.call(packet.battery!);
        }
        yield packet;
      }
    }
    await _notifySubscription?.cancel();
    _notifySubscription = null;
  }
}
