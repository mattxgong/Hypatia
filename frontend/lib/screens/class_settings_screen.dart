import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/class_provider.dart';
import '../services/api_client.dart';

class ClassSettingsScreen extends ConsumerStatefulWidget {
  const ClassSettingsScreen({super.key});

  @override
  ConsumerState<ClassSettingsScreen> createState() =>
      _ClassSettingsScreenState();
}

class _ClassSettingsScreenState extends ConsumerState<ClassSettingsScreen> {
  final _nameController = TextEditingController();
  final _descController = TextEditingController();
  bool _initialized = false;
  bool _saving = false;

  @override
  void dispose() {
    _nameController.dispose();
    _descController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final currentClass = ref.watch(currentClassProvider);
    final theme = Theme.of(context);

    if (currentClass == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (!_initialized) {
      _nameController.text = currentClass.name;
      _descController.text = currentClass.description ?? '';
      _initialized = true;
    }

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/class/${currentClass.id}'),
        ),
        title: const Text('Class Settings'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 600),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('General', style: theme.textTheme.titleMedium),
              const SizedBox(height: 16),
              TextField(
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: 'Class Name',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _descController,
                decoration: const InputDecoration(
                  labelText: 'Description',
                  border: OutlineInputBorder(),
                ),
                maxLines: 3,
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _saving ? null : () => _save(currentClass.id),
                child: _saving
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Save'),
              ),
              const SizedBox(height: 48),
              const Divider(),
              const SizedBox(height: 24),
              Text(
                'Danger Zone',
                style: theme.textTheme.titleMedium?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Deleting a class permanently removes all its files, '
                'wiki pages, and chat history. This cannot be undone.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: () =>
                    _showDeleteConfirmation(currentClass.id, currentClass.name),
                style: OutlinedButton.styleFrom(
                  foregroundColor: theme.colorScheme.error,
                  side: BorderSide(color: theme.colorScheme.error),
                ),
                icon: const Icon(Icons.delete_forever),
                label: const Text('Delete Class'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _save(String classId) async {
    if (_saving) return;
    final name = _nameController.text.trim();
    if (name.isEmpty) return;

    setState(() => _saving = true);
    try {
      await ref
          .read(classListProvider.notifier)
          .updateClass(
            classId,
            name: name,
            description: _descController.text.trim(),
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Class updated'),
            duration: Duration(seconds: 2),
          ),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to update: ${e.detail}')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _showDeleteConfirmation(String classId, String className) {
    final confirmController = TextEditingController();

    showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('Delete Class'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'This will permanently delete "$className" and all its data.',
              ),
              const SizedBox(height: 16),
              Text(
                'Type the class name to confirm:',
                style: Theme.of(dialogContext).textTheme.bodySmall,
              ),
              const SizedBox(height: 8),
              TextField(
                controller: confirmController,
                decoration: InputDecoration(hintText: className),
                onChanged: (_) => setDialogState(() {}),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: confirmController.text.trim() == className
                  ? () async {
                      Navigator.pop(dialogContext);
                      await ref
                          .read(classListProvider.notifier)
                          .delete(classId);
                      if (mounted) context.go('/');
                    }
                  : null,
              style: FilledButton.styleFrom(
                backgroundColor: Theme.of(dialogContext).colorScheme.error,
              ),
              child: const Text('Delete'),
            ),
          ],
        ),
      ),
    );
  }
}
