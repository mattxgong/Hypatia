import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/class_provider.dart';
import '../../services/api_client.dart';
import '../../utils/input_validation.dart';
import '../common/error_card.dart';
import '../common/hypatia_about_button.dart';

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
      data: (classes) {
        // A just-deleted class can still be the "current" one for a frame or
        // two before the router settles. DropdownButtonFormField asserts that
        // its value matches exactly one item, so fall back to no selection
        // rather than taking the whole sidebar down with it.
        final selectedId = classes.any((c) => c.id == currentId)
            ? currentId
            : null;

        return Row(
          children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                // Keyed by the current Class: initialValue is only read once,
                // so without this the field ignores navigation elsewhere.
                key: ValueKey(selectedId),
                initialValue: selectedId,
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
                ],
                hint: const Text('Choose a class'),
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
                ],
                onChanged: (value) {
                  if (value != null) context.go('/class/$value');
                },
              ),
            ),
            // Separate from the list: as list items, picking one and then
            // cancelling left the field showing "New Class".
            PopupMenuButton<String>(
              tooltip: 'Add a class',
              icon: const Icon(Icons.add, size: 20),
              onSelected: (action) => action == 'new'
                  ? showCreateClassDialog(context, ref)
                  : importClassFromBackup(context, ref),
              itemBuilder: (_) => const [
                PopupMenuItem(
                  value: 'new',
                  child: ListTile(
                    leading: Icon(Icons.add),
                    title: Text('New class…'),
                    dense: true,
                  ),
                ),
                PopupMenuItem(
                  value: 'import',
                  child: ListTile(
                    leading: Icon(Icons.file_upload_outlined),
                    title: Text('Import from backup…'),
                    dense: true,
                  ),
                ),
              ],
            ),
            if (selectedId != null)
              IconButton(
                icon: const Icon(Icons.settings_outlined, size: 20),
                tooltip: 'Class settings',
                onPressed: () => context.go('/class/$selectedId/settings'),
                visualDensity: VisualDensity.compact,
              ),
            const HypatiaAboutButton(),
          ],
        );
      },
    );
  }
}

void showCreateClassDialog(BuildContext context, WidgetRef ref) {
  final nameController = TextEditingController();
  final descController = TextEditingController();
  final formKey = GlobalKey<FormState>();
  var creating = false;
  String? error;

  showDialog<void>(
    context: context,
    builder: (dialogContext) => StatefulBuilder(
      builder: (dialogContext, setDialogState) => AlertDialog(
        title: const Text('New Class'),
        content: SizedBox(
          width: 420,
          child: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: nameController,
                  decoration: const InputDecoration(
                    labelText: 'Name',
                    border: OutlineInputBorder(),
                  ),
                  autofocus: true,
                  scrollPhysics: const ClampingScrollPhysics(),
                  maxLength: maxClassNameLength,
                  maxLines: 1,
                  validator: validateClassName,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: descController,
                  decoration: const InputDecoration(
                    labelText: 'Description',
                    border: OutlineInputBorder(),
                  ),
                  maxLength: maxClassDescriptionLength,
                  maxLines: 2,
                  validator: validateClassDescription,
                ),
                if (error != null)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      error!,
                      style: TextStyle(
                        color: Theme.of(dialogContext).colorScheme.error,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          FilledButton(
            // Disabled while creating, so a double click makes one class.
            onPressed: creating
                ? null
                : () async {
                    if (!(formKey.currentState?.validate() ?? false)) return;
                    setDialogState(() {
                      creating = true;
                      error = null;
                    });
                    try {
                      final newClass = await ref
                          .read(classListProvider.notifier)
                          .create(
                            name: nameController.text.trim(),
                            description: descController.text.trim(),
                          );
                      if (dialogContext.mounted) Navigator.pop(dialogContext);
                      if (context.mounted) {
                        context.go('/class/${newClass.id}');
                      }
                    } on ApiException catch (e) {
                      if (dialogContext.mounted) {
                        setDialogState(() {
                          creating = false;
                          error = e.detail;
                        });
                      }
                    }
                  },
            child: Text(creating ? 'Creating…' : 'Create'),
          ),
        ],
      ),
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
