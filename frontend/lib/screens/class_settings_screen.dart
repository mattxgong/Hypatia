import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/class_provider.dart';
import '../providers/settings_provider.dart';
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
  bool _exporting = false;
  bool _importing = false;

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
              Text('Data Management', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                'Export all files, wiki pages, and chat history as a ZIP '
                'backup, or import a class from a backup.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              Wrap(
                spacing: 16,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: _exporting
                        ? null
                        : () =>
                              _exportBackup(currentClass.id, currentClass.name),
                    icon: _exporting
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.file_download_outlined),
                    label: const Text('Export Backup'),
                  ),
                  OutlinedButton.icon(
                    onPressed: _importing ? null : _importBackup,
                    icon: _importing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.file_upload_outlined),
                    label: const Text('Import Class'),
                  ),
                ],
              ),
              const SizedBox(height: 48),
              const Divider(),
              const SizedBox(height: 24),
              Text('Whisper Configuration', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                'Configure the speech-to-text model used for audio/video '
                'transcription.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              _WhisperSettings(),
              const SizedBox(height: 48),
              const Divider(),
              const SizedBox(height: 24),
              Text('Token Usage', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                'Cumulative LLM token usage since the backend started.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              _TokenUsageCard(),
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

  Future<void> _exportBackup(String classId, String className) async {
    if (_exporting) return;
    setState(() => _exporting = true);
    try {
      final api = ref.read(apiClientProvider);
      final bytes = await api.exportClassBackup(classId);

      final safeName = className.replaceAll(RegExp(r'[^\w\-. ]'), '_');
      final outputUri = await FilePicker.saveFile(
        dialogTitle: 'Save Class Backup',
        fileName: 'hypatia-backup-$safeName.zip',
        bytes: bytes,
        type: FileType.custom,
        allowedExtensions: ['zip'],
      );
      if (outputUri == null) return;

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Backup exported successfully')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Export failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _importBackup() async {
    final files = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['zip'],
      dialogTitle: 'Select Backup ZIP',
    );
    if (files.isEmpty || files.first.path == null) return;

    setState(() => _importing = true);
    try {
      final api = ref.read(apiClientProvider);
      final importResult = await api.importClassBackup(files.first.path!);

      ref.invalidate(classListProvider);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Imported "${importResult['name']}" — '
              '${importResult['file_count']} files, '
              '${importResult['page_count']} pages',
            ),
            duration: const Duration(seconds: 4),
          ),
        );
        context.go('/class/${importResult['id']}');
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Import failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _importing = false);
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

class _WhisperSettings extends ConsumerStatefulWidget {
  @override
  ConsumerState<_WhisperSettings> createState() => _WhisperSettingsState();
}

class _WhisperSettingsState extends ConsumerState<_WhisperSettings> {
  static const _modelSizes = ['tiny', 'base', 'small', 'medium'];
  static const _devices = ['cpu', 'cuda'];

  bool _saving = false;

  @override
  Widget build(BuildContext context) {
    final settingsAsync = ref.watch(fullSettingsProvider);
    final settings = settingsAsync.valueOrNull ?? {};
    final currentSize = (settings['whisper_model_size'] as String?) ?? 'base';
    final currentDevice = (settings['whisper_device'] as String?) ?? 'cpu';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _modelSizes.contains(currentSize)
              ? currentSize
              : 'base',
          decoration: const InputDecoration(
            labelText: 'Model Size',
            border: OutlineInputBorder(),
            helperText:
                'Larger models are more accurate but slower and use more RAM',
          ),
          items: _modelSizes
              .map((s) => DropdownMenuItem(value: s, child: Text(s)))
              .toList(),
          onChanged: _saving
              ? null
              : (value) async {
                  if (value == null) return;
                  setState(() => _saving = true);
                  await ref
                      .read(fullSettingsProvider.notifier)
                      .updateFields(whisperModelSize: value);
                  if (mounted) setState(() => _saving = false);
                },
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _devices.contains(currentDevice)
              ? currentDevice
              : 'cpu',
          decoration: const InputDecoration(
            labelText: 'Device',
            border: OutlineInputBorder(),
            helperText: 'Use CUDA for GPU acceleration (requires NVIDIA GPU)',
          ),
          items: _devices
              .map(
                (d) => DropdownMenuItem(
                  value: d,
                  child: Text(d == 'cuda' ? 'GPU (CUDA)' : 'CPU'),
                ),
              )
              .toList(),
          onChanged: _saving
              ? null
              : (value) async {
                  if (value == null) return;
                  setState(() => _saving = true);
                  await ref
                      .read(fullSettingsProvider.notifier)
                      .updateFields(whisperDevice: value);
                  if (mounted) setState(() => _saving = false);
                },
        ),
      ],
    );
  }
}

final _usageProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final apiClient = ref.read(apiClientProvider);
  return apiClient.getUsage();
});

class _TokenUsageCard extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usageAsync = ref.watch(_usageProvider);
    final theme = Theme.of(context);

    return usageAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) =>
          Text('Could not load usage data', style: theme.textTheme.bodySmall),
      data: (usage) {
        final input = usage['input_tokens'] as int? ?? 0;
        final output = usage['output_tokens'] as int? ?? 0;
        final requests = usage['request_count'] as int? ?? 0;

        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    _UsageStat(label: 'Requests', value: '$requests'),
                    const SizedBox(width: 32),
                    _UsageStat(
                      label: 'Input Tokens',
                      value: _formatNumber(input),
                    ),
                    const SizedBox(width: 32),
                    _UsageStat(
                      label: 'Output Tokens',
                      value: _formatNumber(output),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: () => ref.invalidate(_usageProvider),
                    icon: const Icon(Icons.refresh, size: 16),
                    label: const Text('Refresh'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static String _formatNumber(int n) {
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}K';
    return n.toString();
  }
}

class _UsageStat extends StatelessWidget {
  const _UsageStat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value, style: theme.textTheme.titleMedium),
        Text(label, style: theme.textTheme.bodySmall),
      ],
    );
  }
}
