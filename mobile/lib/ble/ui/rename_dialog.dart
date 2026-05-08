import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../../i18n/strings.g.dart';
import '../wt901_commander.dart';

class RenameDialog extends StatefulWidget {
  final BluetoothDevice device;
  const RenameDialog({super.key, required this.device});

  @override
  State<RenameDialog> createState() => _RenameDialogState();
}

class _RenameDialogState extends State<RenameDialog> {
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final id = int.tryParse(_ctrl.text);
    if (id == null || id < 0 || id > 255) return;
    final commander = WT901Commander(widget.device);
    await commander.rename(id);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final t = Translations.of(context);
    return shad.AlertDialog(
      title: Text(t.ble.rename.dialogTitle),
      content: shad.TextField(
        controller: _ctrl,
        placeholder: Text(t.ble.rename.placeholder),
        keyboardType: TextInputType.number,
      ),
      actions: [
        shad.GhostButton(
          onPressed: () => Navigator.pop(context),
          child: Text(t.ble.rename.cancel),
        ),
        shad.PrimaryButton(
          onPressed: _save,
          child: Text(t.ble.rename.save),
        ),
      ],
    );
  }
}