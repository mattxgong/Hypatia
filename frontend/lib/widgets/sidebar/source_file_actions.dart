import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/source_file.dart';
import '../../providers/file_provider.dart';
import '../../providers/wiki_provider.dart';
import '../../services/api_client.dart';
import '../common/action_menu.dart';
import '../source_viewer/source_viewer.dart';

enum _FileAction { open, retry, delete }

/// The right-click (or long-press) menu of a source file: a bottom sheet on a
/// phone.
Future<void> showSourceFileMenu(
  BuildContext context,
  WidgetRef ref,
  String classId,
  SourceFile file,
  Offset position,
) async {
  final action = await showActionMenu<_FileAction>(
    context,
    title: file.originalFilename,
    position: position,
    items: [
      ActionMenuItem(
        value: _FileAction.open,
        icon: Icons.open_in_new,
        label: 'Open',
        enabled: file.convertedPath != null,
      ),
      if (file.status == FileStatus.error)
        const ActionMenuItem(
          value: _FileAction.retry,
          icon: Icons.refresh,
          label: 'Retry',
        ),
      const ActionMenuItem(
        value: _FileAction.delete,
        icon: Icons.delete_outline,
        label: 'Delete…',
      ),
    ],
  );
  if (action == null || !context.mounted) return;
  switch (action) {
    case _FileAction.open:
      showConvertedSourceViewer(context, classId, file);
    case _FileAction.retry:
      await retrySourceFile(context, ref, classId, file);
    case _FileAction.delete:
      await confirmDeleteSourceFile(context, ref, classId, file);
  }
}

Future<void> retrySourceFile(
  BuildContext context,
  WidgetRef ref,
  String classId,
  SourceFile file,
) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    await ref.read(apiClientProvider).retryFile(classId, file.id);
    ref.invalidate(fileListProvider(classId));
    ref.read(filePollingProvider(classId).notifier).startPolling();
  } on ApiException catch (e) {
    messenger.showSnackBar(
      SnackBar(
        content: Text('Could not retry ${file.originalFilename}: ${e.detail}'),
      ),
    );
  }
}

Future<void> confirmDeleteSourceFile(
  BuildContext context,
  WidgetRef ref,
  String classId,
  SourceFile file,
) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text('Delete ${file.originalFilename}?'),
      content: const Text(
        'The file is removed, along with wiki pages that only it supports. '
        'Pages you have edited are kept, and pages with other sources lose '
        'only this one.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: Theme.of(context).colorScheme.error,
            foregroundColor: Theme.of(context).colorScheme.onError,
          ),
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('Delete'),
        ),
      ],
    ),
  );
  if (confirmed != true || !context.mounted) return;

  final messenger = ScaffoldMessenger.of(context);
  try {
    await ref.read(apiClientProvider).deleteFile(classId, file.id);
    messenger.showSnackBar(
      SnackBar(content: Text('Deleted ${file.originalFilename}')),
    );
  } on ApiException catch (e) {
    messenger.showSnackBar(
      SnackBar(
        content: Text('Could not delete ${file.originalFilename}: ${e.detail}'),
      ),
    );
  } finally {
    ref.invalidate(fileListProvider(classId));
    ref.invalidate(wikiTreeProvider(classId));
  }
}
