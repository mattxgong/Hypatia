import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:pdfrx/pdfrx.dart';

import '../../models/source_file.dart';
import '../../providers/class_provider.dart';
import '../../services/api_client.dart';
import '../wiki_viewer/wiki_viewer.dart';

final _sourceFileProvider =
    FutureProvider.family<SourceFile?, SourceViewerRequest>((
      ref,
      request,
    ) async {
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
      return match.first;
    });

class SourceViewerDialog extends ConsumerWidget {
  const SourceViewerDialog({super.key, required this.request});

  final SourceViewerRequest request;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final screenSize = MediaQuery.of(context).size;

    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      child: SizedBox(
        width: screenSize.width * 0.8,
        height: screenSize.height * 0.8,
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: theme.dividerColor)),
              ),
              child: Row(
                children: [
                  Icon(_fileTypeIcon(request.fileRef), size: 20),
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

  IconData _fileTypeIcon(String filename) {
    final ext = filename.split('.').last.toLowerCase();
    if ({'mp4', 'avi', 'mov', 'mkv'}.contains(ext)) return Icons.videocam;
    if ({'mp3', 'wav', 'm4a'}.contains(ext)) return Icons.audiotrack;
    if (ext == 'pdf') return Icons.picture_as_pdf;
    if ({'png', 'jpg', 'jpeg', 'gif'}.contains(ext)) return Icons.image;
    return Icons.insert_drive_file_outlined;
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

    final fileAsync = ref.watch(_sourceFileProvider(request));

    return fileAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error loading file: $e')),
      data: (file) {
        if (file == null) {
          return const Center(child: Text('File not found'));
        }
        return _buildViewer(context, ref, file, classId);
      },
    );
  }

  Widget _buildViewer(
    BuildContext context,
    WidgetRef ref,
    SourceFile file,
    String classId,
  ) {
    final apiClient = ref.read(apiClientProvider);

    switch (file.fileType) {
      case FileType.video:
      case FileType.audio:
        final rawUrl = apiClient.getFileRawUrl(classId, file.id);
        final seekSeconds = _parseSeekSeconds(request.location);
        return _MediaViewer(
          url: rawUrl,
          seekSeconds: seekSeconds,
          isAudio: file.fileType == FileType.audio,
        );

      case FileType.pdf:
        final rawUrl = apiClient.getFileRawUrl(classId, file.id);
        final page = _parsePage(request.location);
        return _PdfViewer(url: rawUrl, initialPage: page);

      case FileType.image:
        final rawUrl = apiClient.getFileRawUrl(classId, file.id);
        return _ImageViewer(url: rawUrl);

      default:
        return _TextViewer(classId: classId, fileId: file.id);
    }
  }

  int _parseSeekSeconds(String loc) {
    if (loc.startsWith('t:')) return int.tryParse(loc.substring(2)) ?? 0;
    return 0;
  }

  int _parsePage(String loc) {
    if (loc.startsWith('p:')) return int.tryParse(loc.substring(2)) ?? 1;
    return 1;
  }
}

class _MediaViewer extends StatefulWidget {
  const _MediaViewer({
    required this.url,
    required this.seekSeconds,
    required this.isAudio,
  });

  final String url;
  final int seekSeconds;
  final bool isAudio;

  @override
  State<_MediaViewer> createState() => _MediaViewerState();
}

class _MediaViewerState extends State<_MediaViewer> {
  late final Player _player;
  late final VideoController _controller;
  bool _seeked = false;

  @override
  void initState() {
    super.initState();
    _player = Player();
    _controller = VideoController(_player);
    _player.open(Media(widget.url));

    if (widget.seekSeconds > 0) {
      _player.stream.playing.listen((playing) {
        if (playing && !_seeked) {
          _seeked = true;
          _player.seek(Duration(seconds: widget.seekSeconds));
        }
      });
    }
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.isAudio) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.audiotrack, size: 64),
            const SizedBox(height: 24),
            SizedBox(
              width: 400,
              height: 100,
              child: Video(controller: _controller),
            ),
          ],
        ),
      );
    }
    return Video(controller: _controller);
  }
}

class _PdfViewer extends StatelessWidget {
  const _PdfViewer({required this.url, required this.initialPage});

  final String url;
  final int initialPage;

  @override
  Widget build(BuildContext context) {
    return PdfViewer.uri(Uri.parse(url), initialPageNumber: initialPage);
  }
}

class _ImageViewer extends StatelessWidget {
  const _ImageViewer({required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    return InteractiveViewer(
      minScale: 0.5,
      maxScale: 4.0,
      child: Center(
        child: Image.network(
          url,
          fit: BoxFit.contain,
          loadingBuilder: (context, child, progress) {
            if (progress == null) return child;
            return Center(
              child: CircularProgressIndicator(
                value: progress.expectedTotalBytes != null
                    ? progress.cumulativeBytesLoaded /
                          progress.expectedTotalBytes!
                    : null,
              ),
            );
          },
          errorBuilder: (context, error, stack) => Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.broken_image, size: 48),
                const SizedBox(height: 8),
                Text('Failed to load image: $error'),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TextViewer extends ConsumerWidget {
  const _TextViewer({required this.classId, required this.fileId});

  final String classId;
  final String fileId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return FutureBuilder<String>(
      future: ref.read(apiClientProvider).getFileConverted(classId, fileId),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(child: Text('Error: ${snapshot.error}'));
        }
        final content = snapshot.data ?? '';
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
