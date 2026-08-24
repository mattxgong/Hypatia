import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/class_provider.dart';
import '../../providers/file_provider.dart';
import '../../services/api_client.dart';

class AddFileButton extends ConsumerWidget {
  const AddFileButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: () => _pickAndUpload(context, ref),
        icon: const Icon(Icons.add, size: 18),
        label: const Text('Add Files'),
      ),
    );
  }

  Future<void> _pickAndUpload(BuildContext context, WidgetRef ref) async {
    final classId = ref.read(currentClassIdProvider);
    if (classId == null) return;

    final files = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: [
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
      ],
    );

    if (files.isEmpty) return;

    final paths = files
        .where((PlatformFile f) => f.path != null)
        .map((PlatformFile f) => f.path!)
        .toList();

    if (paths.isEmpty) return;

    final apiClient = ref.read(apiClientProvider);
    try {
      await apiClient.uploadFiles(classId, paths);
      ref.invalidate(fileListProvider(classId));
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${paths.length} file(s) uploaded'),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Upload failed: ${e.detail}')));
      }
    }
  }
}
