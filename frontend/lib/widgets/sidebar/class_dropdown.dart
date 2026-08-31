import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/class_provider.dart';
import '../../services/api_client.dart';
import '../common/error_card.dart';

class ClassDropdown extends ConsumerWidget {
  const ClassDropdown({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classesAsync = ref.watch(classListProvider);
    final currentId = ref.watch(currentClassIdProvider);
    final theme = Theme.of(context);

    return classesAsync.when(
      loading: () => const LinearProgressIndicator(),
      error: (e, _) => ErrorCard(error: e, compact: true),
      data: (classes) => Row(
        children: [
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: currentId,
              decoration: InputDecoration(
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide.none,
                ),
                filled: true,
                fillColor: theme.colorScheme.surfaceContainerHigh,
              ),
              isExpanded: true,
              selectedItemBuilder: (context) => [
                ...classes.map(
                  (c) => Align(
                    alignment: Alignment.centerLeft,
                    child: Text(c.name, overflow: TextOverflow.ellipsis),
                  ),
                ),
                const Align(
                  alignment: Alignment.centerLeft,
                  child: Text('New Class'),
                ),
                const Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Import Class'),
                ),
              ],
              items: [
                ...classes.map(
                  (c) => DropdownMenuItem<String>(
                    value: c.id,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(c.name, overflow: TextOverflow.ellipsis),
                        Text(
                          '${c.fileCount} files, ${c.pageCount} pages',
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: theme.colorScheme.onSurface.withValues(
                              alpha: 0.5,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const DropdownMenuItem<String>(
                  value: '__new__',
                  child: Row(
                    children: [
                      Icon(Icons.add, size: 16),
                      SizedBox(width: 8),
                      Text('New Class'),
                    ],
                  ),
                ),
                const DropdownMenuItem<String>(
                  value: '__import__',
                  child: Row(
                    children: [
                      Icon(Icons.file_upload_outlined, size: 16),
                      SizedBox(width: 8),
                      Text('Import Class'),
                    ],
                  ),
                ),
              ],
              onChanged: (value) {
                if (value == '__new__') {
                  showCreateClassDialog(context, ref);
                } else if (value == '__import__') {
                  importClassFromBackup(context, ref);
                } else if (value != null) {
                  context.go('/class/$value');
                }
              },
            ),
          ),
          if (currentId != null)
            IconButton(
              icon: const Icon(Icons.settings_outlined, size: 20),
              tooltip: 'Class settings',
              onPressed: () => context.go('/class/$currentId/settings'),
              visualDensity: VisualDensity.compact,
            ),
        ],
      ),
    );
  }
}

void showCreateClassDialog(BuildContext context, WidgetRef ref) {
  final nameController = TextEditingController();
  final descController = TextEditingController();

  showDialog<void>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('New Class'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(
                labelText: 'Name',
                border: OutlineInputBorder(),
              ),
              autofocus: true,
              scrollPhysics: const ClampingScrollPhysics(),
              maxLines: 1,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: descController,
              decoration: const InputDecoration(
                labelText: 'Description',
                border: OutlineInputBorder(),
              ),
              maxLines: 2,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () async {
            final name = nameController.text.trim();
            if (name.isEmpty) return;
            final newClass = await ref
                .read(classListProvider.notifier)
                .create(name: name, description: descController.text.trim());
            if (dialogContext.mounted) Navigator.pop(dialogContext);
            if (context.mounted) {
              context.go('/class/${newClass.id}');
            }
          },
          child: const Text('Create'),
        ),
      ],
    ),
  );
}

class ProviderOption {
  const ProviderOption({required this.id, required this.label});
  final String id;
  final String label;
}

const providerOptions = [
  ProviderOption(id: 'copilot', label: 'GitHub Copilot'),
  ProviderOption(id: 'anthropic', label: 'Anthropic Claude'),
  ProviderOption(id: 'openai', label: 'OpenAI'),
  ProviderOption(id: 'ollama', label: 'Ollama (Local)'),
  ProviderOption(id: 'copilot-ollama', label: 'Copilot + Ollama'),
];

Future<void> importClassFromBackup(BuildContext context, WidgetRef ref) async {
  final messenger = ScaffoldMessenger.of(context);
  final router = GoRouter.of(context);
  final api = ref.read(apiClientProvider);

  final files = await FilePicker.pickFiles(
    type: FileType.custom,
    allowedExtensions: ['zip'],
    dialogTitle: 'Select Backup ZIP',
  );
  if (files.isEmpty || files.first.path == null) return;

  try {
    final importResult = await api.importClassBackup(files.first.path!);

    ref.invalidate(classListProvider);

    messenger.showSnackBar(
      SnackBar(
        content: Text(
          'Imported "${importResult['name']}" — '
          '${importResult['file_count']} files, '
          '${importResult['page_count']} pages',
        ),
        duration: const Duration(seconds: 4),
      ),
    );
    router.go('/class/${importResult['id']}');
  } on ApiException catch (e) {
    messenger.showSnackBar(
      SnackBar(content: Text('Import failed: ${e.detail}')),
    );
  }
}
