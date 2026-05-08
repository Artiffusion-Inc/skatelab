import 'package:flutter_blue_plus/flutter_blue_plus.dart';

class WT901Commander {
  final BluetoothDevice device;
  BluetoothCharacteristic? _writeCharacteristic;

  WT901Commander(this.device);

  static final List<int> _unlock = [0xFF, 0xAA, 0x69, 0x88, 0xB5];
  static final List<int> _save = [0xFF, 0xAA, 0x00, 0x00, 0x00];

  Future<BluetoothCharacteristic> _getWriteCharacteristic() async {
    if (_writeCharacteristic != null) return _writeCharacteristic!;
    final services = await device.discoverServices();
    final target = services.firstWhere(
      (s) => s.uuid.toString().toLowerCase().contains('ffe0'),
      orElse: () => services.first,
    );
    _writeCharacteristic = target.characteristics.firstWhere(
      (c) => c.properties.write || c.properties.writeWithoutResponse,
      orElse: () => target.characteristics.first,
    );
    return _writeCharacteristic!;
  }

  Future<void> _sendCommand(List<int> cmd) async {
    try {
      final c = await _getWriteCharacteristic();
      await c.write(cmd, withoutResponse: true);
    } catch (_) {
      _writeCharacteristic = null;
      rethrow;
    }
  }

  /// Unlock device for configuration
  Future<void> unlock() async => _sendCommand(_unlock);

  /// Save configuration
  Future<void> save() async => _sendCommand(_save);

  /// Set return rate. rateCode: 0x01=0.2Hz, 0x02=0.5Hz, 0x03=1Hz, 0x04=2Hz, 0x05=5Hz, 0x06=10Hz, 0x07=20Hz, 0x08=50Hz, 0x09=100Hz, 0x0B=200Hz
  Future<void> setReturnRate(int rateCode) async {
    await unlock();
    await _sendCommand([0xFF, 0xAA, 0x03, rateCode & 0xFF, 0x00]);
    await save();
  }

  /// Read battery voltage (register 0x5C). Response parsed by notification listener.
  Future<void> requestBattery() async {
    await _sendCommand([0xFF, 0xAA, 0x27, 0x5C, 0x00]);
  }

  /// Rename device (set device address). newId: 0-255.
  Future<void> rename(int newId) async {
    await unlock();
    await _sendCommand([0xFF, 0xAA, 0x75, newId & 0xFF, 0x00]);
    await save();
  }
}
