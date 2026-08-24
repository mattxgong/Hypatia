import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/class_provider.dart';
import '../../services/api_client.dart';
import '../wiki_viewer/wiki_viewer.dart';

final _sourceContentProvider =
    FutureProvider.family<String?, SourceViewerRequest>((ref, request) async {
      final classId = ref.watch(currentClassIdProvider);
      if (classId == null) return null;

      final apiClient = ref.read(apiClientProvider);
      final files = await apiClient.listFiles(classId);
      final match = files.where(
        (f) =>
            f.originalFilename == request.fileRef ||
            f.rawPath.endsWith(request.fileRef),
      );
      if (match.isEmpty) return null;
      return apiClient.getFileConverted(classId, match.first.id);
    });

class SourceViewerDialog extends ConsumerWidget {
  const SourceViewerDialog({super.key, required this.request});

  final SourceViewerRequest request;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    return Dialog(
      insetPadding: const EdgeInsets.all(32),
      child: SizedBox(
        width: 800,
        height: 600,
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: theme.dividerColor)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.insert_drive_file_outlined, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      request.fileRef,
                      style: theme.textTheme.titleSmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (request.location.isNotEmpty)
                    Chip(
                      label: Text(
                        _formatLocation(request.location),
                        style: theme.textTheme.labelSmall,
                      ),
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                    ),
                  const SizedBox(width: 8),
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),
            Expanded(child: _SourceContent(request: request)),
          ],
        ),
      ),
    );
  }

  String _formatLocation(String loc) {
    if (loc.startsWith('t:')) {
      final seconds = int.tryParse(loc.substring(2)) ?? 0;
      final m = seconds ~/ 60;
      final s = seconds % 60;
      return '${m}m ${s}s';
    }
    if (loc.startsWith('p:')) return 'Page ${loc.substring(2)}';
    return loc;
  }
}

class _SourceContent extends ConsumerWidget {
  const _SourceContent({required this.request});

  final SourceViewerRequest request;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    if (classId == null) {
      return const Center(child: Text('No class selected'));
    }

    final contentAsync = ref.watch(_sourceContentProvider(request));

    return contentAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error loading file: $e')),
      data: (content) {
        if (content == null) {
          return const Center(child: Text('File not found'));
        }
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: SelectableText(
            content,
            style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
          ),
        );
      },
    );
  }
}

void showSourceViewer(BuildContext context, SourceViewerRequest request) {
  showDialog<void>(
    context: context,
    builder: (_) => SourceViewerDialog(request: request),
  );
}
