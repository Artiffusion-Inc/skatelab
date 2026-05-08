import 'package:flutter/material.dart';
import 'package:shadcn_flutter/shadcn_flutter.dart' as shad;
import '../../i18n/strings.g.dart';
import '../../theme/app_theme.dart';

class ExportResultScreen extends StatelessWidget {
  final String? exportPath;
  final VoidCallback onNewCapture;
  const ExportResultScreen({
    super.key,
    required this.exportPath,
    required this.onNewCapture,
  });

  @override
  Widget build(BuildContext context) {
    final success = exportPath != null;
    final t = Translations.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(t.export.title)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (success)
                shad.Alert(
                  leading: const Icon(Icons.check_circle, size: 48, color: AppColors.success),
                  title: Text(t.export.success),
                  content: Container(
                    margin: const EdgeInsets.only(top: 8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: SelectableText(
                      exportPath!,
                      style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                    ),
                  ),
                )
              else
                shad.Alert.destructive(
                  leading: const Icon(Icons.error, size: 48),
                  title: Text(t.export.error),
                ),
              const SizedBox(height: 32),
              shad.PrimaryButton(
                onPressed: onNewCapture,
                leading: const Icon(Icons.add),
                child: Text(t.export.newCapture),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
