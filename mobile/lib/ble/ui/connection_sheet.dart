import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../../i18n/strings.g.dart';
import '../../../theme/app_theme.dart';

class ConnectionSheet extends StatelessWidget {
  final BluetoothDevice device;
  final VoidCallback onLeft;
  final VoidCallback onRight;

  const ConnectionSheet({
    super.key,
    required this.device,
    required this.onLeft,
    required this.onRight,
  });

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            title: Text(device.platformName),
            subtitle: Text(device.remoteId.str),
          ),
          const shad.Divider(),
          ListTile(
            leading: const Icon(Icons.skip_previous, color: AppColors.leftSide),
            title: Text(t.ble.left),
            onTap: () {
              onLeft();
              Navigator.pop(context);
            },
          ),
          ListTile(
            leading: const Icon(Icons.skip_next, color: AppColors.rightSide),
            title: Text(t.ble.right),
            onTap: () {
              onRight();
              Navigator.pop(context);
            },
          ),
        ],
      ),
    );
  }
}
