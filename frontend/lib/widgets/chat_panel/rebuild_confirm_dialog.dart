import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../services/api_client.dart';

/// Shows what `/rebuild` would change and asks the user to confirm it.
Future<bool> confirmRebuild(
  BuildContext context,
  WidgetRef ref,
  String classId,
) async {
  final messenger = ScaffoldMessenger.of(context);
  final Map<String, dynamic> preview;
  try {
    preview = await ref.read(apiClientProvider).rebuildWiki(classId);
  } on ApiException catch (e) {
    messenger.showSnackBar(
      SnackBar(content: Text('Cannot rebuild: ${e.detail}')),
    );
    return false;
  }
  if (!context.mounted) return false;
  return await showDialog<bool>(
        context: context,
        builder: (_) => RebuildConfirmDialog(preview: preview),
      ) ??
      false;
}

class RebuildConfirmDialog extends StatelessWidget {
  const RebuildConfirmDialog({super.key, required this.preview});

  final Map<String, dynamic> preview;

  List<String> _paths(String key) =>
      (preview[key] as List<dynamic>? ?? const []).cast<String>();

  static String _pageName(String path) => path
      .split('/')
      .last
      .replaceFirst(RegExp(r'\.md$'), '')
      .replaceAll('-', ' ');

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sources = preview['source_file_count'] as int? ?? 0;
    final tokens = preview['estimated_tokens'] as int? ?? 0;
    final regenerated = _paths('pages_to_delete');
    final userEdited = _paths('pages_preserved_user_edited').length;
    final synthesis = _paths('pages_preserved_synthesis').length;

    return AlertDialog(
      title: const Text('Rebuild the wiki?'),
      content: SizedBox(
        width: 440,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'The AI will re-read $sources '
              '${sources == 1 ? 'source' : 'sources'} (about $tokens tokens) '
              'and write the wiki again.',
            ),
            const SizedBox(height: 12),
            Text(
              'Kept unchanged: $userEdited '
              '${userEdited == 1 ? 'page' : 'pages'} you edited and '
              '$synthesis synthesis ${synthesis == 1 ? 'page' : 'pages'}.',
            ),
            if (regenerated.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                '${regenerated.length} '
                '${regenerated.length == 1 ? 'page' : 'pages'} will be '
                'regenerated. Any the AI does not write again will be removed. '
                'If a source fails to re-ingest, its pages are kept.',
              ),
              const SizedBox(height: 8),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 180),
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final path in regenerated)
                      Text(
                        '• ${_pageName(path)}',
                        style: theme.textTheme.bodySmall,
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, true),
          child: const Text('Rebuild'),
        ),
      ],
    );
  }
}
