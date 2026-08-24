import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/class_provider.dart';

class ClassDropdown extends ConsumerWidget {
  const ClassDropdown({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classesAsync = ref.watch(classListProvider);
    final currentId = ref.watch(currentClassIdProvider);
    final theme = Theme.of(context);

    return classesAsync.when(
      loading: () => const LinearProgressIndicator(),
      error: (e, _) => Text('Error: $e', style: theme.textTheme.bodySmall),
      data: (classes) => DropdownButtonFormField<String>(
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
        items: [
          ...classes.map(
            (c) => DropdownMenuItem<String>(
              value: c.id,
              child: Text(c.name, overflow: TextOverflow.ellipsis),
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
        ],
        onChanged: (value) {
          if (value == '__new__') {
            _showCreateClassDialog(context, ref);
          } else if (value != null) {
            context.go('/class/$value');
          }
        },
      ),
    );
  }

  void _showCreateClassDialog(BuildContext context, WidgetRef ref) {
    final nameController = TextEditingController();
    final descController = TextEditingController();

    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('New Class'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(labelText: 'Name'),
              autofocus: true,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: descController,
              decoration: const InputDecoration(labelText: 'Description'),
            ),
          ],
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
}
