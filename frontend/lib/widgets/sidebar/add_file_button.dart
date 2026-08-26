import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/class_provider.dart';
import '../../providers/upload_provider.dart';

const allowedExtensions = [
  'pdf',
  'docx',
  'pptx',
  'xlsx',
  'csv',
  'txt',
  'md',
  'mp4',
  'avi',
  'mov',
  'mkv',
  'mp3',
  'wav',
  'm4a',
  'png',
  'jpg',
  'jpeg',
  'gif',
];

class AddFileButton extends ConsumerWidget {
  const AddFileButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final uploadState = ref.watch(uploadProgressProvider);

    ref.listen(uploadProgressProvider, (prev, next) {
      if (next.status == UploadStatus.complete) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${next.filesTotal} file(s) uploaded'),
            duration: const Duration(seconds: 2),
          ),
        );
        Future.delayed(const Duration(seconds: 1), () {
          ref.read(uploadProgressProvider.notifier).reset();
        });
      } else if (next.status == UploadStatus.error) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Upload failed: ${next.errorMessage}'),
            action: SnackBarAction(
              label: 'Retry',
              onPressed: () =>
                  ref.read(uploadProgressProvider.notifier).retry(),
            ),
          ),
        );
      }
    });

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (uploadState.status == UploadStatus.uploading)
          _UploadProgressIndicator(state: uploadState, ref: ref),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: uploadState.status == UploadStatus.uploading
                ? null
                : () => _pickAndUpload(context, ref),
            icon: const Icon(Icons.add, size: 18),
            label: const Text('Add Files'),
          ),
        ),
      ],
    );
  }

  Future<void> _pickAndUpload(BuildContext context, WidgetRef ref) async {
    final classId = ref.read(currentClassIdProvider);
    if (classId == null) return;

    final files = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: allowedExtensions,
    );

    if (files.isEmpty) return;

    final paths = files
        .where((PlatformFile f) => f.path != null)
        .map((PlatformFile f) => f.path!)
        .toList();

    if (paths.isEmpty) return;

    unawaited(ref.read(uploadProgressProvider.notifier).uploadFiles(paths));
  }
}

class _UploadProgressIndicator extends StatelessWidget {
  const _UploadProgressIndicator({required this.state, required this.ref});

  final UploadState state;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final percent = (state.progress * 100).toInt();

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  state.currentFileName,
                  style: theme.textTheme.labelSmall,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text('$percent%', style: theme.textTheme.labelSmall),
              const SizedBox(width: 4),
              SizedBox(
                width: 20,
                height: 20,
                child: IconButton(
                  icon: const Icon(Icons.close, size: 12),
                  onPressed: () =>
                      ref.read(uploadProgressProvider.notifier).cancel(),
                  padding: EdgeInsets.zero,
                  tooltip: 'Cancel upload',
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          LinearProgressIndicator(value: state.progress),
          if (state.filesTotal > 1) ...[
            const SizedBox(height: 2),
            Text(
              '${state.filesDone} of ${state.filesTotal} files',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
