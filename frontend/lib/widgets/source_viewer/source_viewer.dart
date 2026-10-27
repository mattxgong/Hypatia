import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:pdfrx/pdfrx.dart';

import '../../models/source_file.dart';
import '../../providers/class_provider.dart';
import '../../providers/file_provider.dart';
import '../../services/api_client.dart';
import '../../utils/frontmatter.dart';
import '../common/error_card.dart';
import '../wiki_viewer/wiki_viewer.dart';

/// The source file a citation names (by ID or filename). Keyed by a record,
/// which compares by value, and disposed with the dialog: keyed by the request
/// object, every citation click added a provider that was never freed.
final _sourceFileProvider = FutureProvider.autoDispose
    .family<SourceFile?, ({String classId, String fileRef})>((ref, key) async {
      // The sidebar's cached list, rather than fetching every file again.
      final files = await ref.watch(fileListProvider(key.classId).future);
      for (final f in files) {
        if (f.id == key.fileRef ||
            f.originalFilename == key.fileRef ||
            f.rawPath.endsWith(key.fileRef)) {
          return f;
        }
      }
      return null;
    });

class SourceViewerDialog extends ConsumerWidget {
  const SourceViewerDialog({super.key, required this.request});

  final SourceViewerRequest request;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final screenSize = MediaQuery.of(context).size;
    final classId = ref.watch(currentClassIdProvider);
    // Citations name files by ID; show the file's name once it's known.
    final file = classId == null
        ? null
        : ref
              .watch(
                _sourceFileProvider((
                  classId: classId,
                  fileRef: request.fileRef,
                )),
              )
              .valueOrNull;
    final title = file?.originalFilename ?? request.fileRef;

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
                  Icon(_fileTypeIcon(title), size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      title,
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
                    tooltip: 'Close',
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
    if (loc.startsWith('s:')) {
      return '§ ${loc.substring(2).replaceAll(RegExp(r'[-_]+'), ' ')}';
    }
    if (loc.startsWith('l:')) return 'Line ${loc.substring(2)}';
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

    final fileAsync = ref.watch(
      _sourceFileProvider((classId: classId, fileRef: request.fileRef)),
    );

    return fileAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: ErrorCard(error: e)),
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
          headers: apiClient.authHeaders,
          seekSeconds: seekSeconds,
          isAudio: file.fileType == FileType.audio,
        );

      case FileType.pdf:
        final rawUrl = apiClient.getFileRawUrl(classId, file.id);
        final page = _parsePage(request.location);
        return _PdfViewer(
          url: rawUrl,
          headers: apiClient.authHeaders,
          initialPage: page,
        );

      case FileType.image:
        final rawUrl = apiClient.getFileRawUrl(classId, file.id);
        return _ImageViewer(url: rawUrl, headers: apiClient.authHeaders);

      default:
        return _TextViewer(
          classId: classId,
          fileId: file.id,
          location: request.location,
        );
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
    required this.headers,
    required this.seekSeconds,
    required this.isAudio,
  });

  final String url;
  final Map<String, String> headers;
  final int seekSeconds;
  final bool isAudio;

  @override
  State<_MediaViewer> createState() => _MediaViewerState();
}

class _MediaViewerState extends State<_MediaViewer> {
  late final Player _player;
  late final VideoController _controller;

  @override
  void initState() {
    super.initState();
    _player = Player();
    _controller = VideoController(_player);
    // Opened at the cited time, rather than played from 0 and then seeked.
    _player.open(
      Media(
        widget.url,
        httpHeaders: widget.headers,
        start: Duration(seconds: widget.seekSeconds),
      ),
    );
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
  const _PdfViewer({
    required this.url,
    required this.headers,
    required this.initialPage,
  });

  final String url;
  final Map<String, String> headers;
  final int initialPage;

  @override
  Widget build(BuildContext context) {
    return PdfViewer.uri(
      Uri.parse(url),
      headers: headers,
      initialPageNumber: initialPage,
    );
  }
}

class _ImageViewer extends StatelessWidget {
  const _ImageViewer({required this.url, required this.headers});

  final String url;
  final Map<String, String> headers;

  @override
  Widget build(BuildContext context) {
    return InteractiveViewer(
      minScale: 0.5,
      maxScale: 4.0,
      child: Center(
        child: Image.network(
          url,
          headers: headers,
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

class _TextViewer extends ConsumerStatefulWidget {
  const _TextViewer({
    required this.classId,
    required this.fileId,
    this.location = '',
  });

  final String classId;
  final String fileId;
  final String location;

  @override
  ConsumerState<_TextViewer> createState() => _TextViewerState();
}

class _TextViewerState extends ConsumerState<_TextViewer> {
  // Loaded once: created in build, a new request went out on every rebuild.
  late final Future<String> _content = ref
      .read(apiClientProvider)
      .getFileConverted(widget.classId, widget.fileId);
  final _scroll = ScrollController();
  final _targetKey = GlobalKey();
  int? _target;
  bool _scrolled = false;

  static const _style = TextStyle(fontFamily: 'monospace', fontSize: 13);
  static const _estimatedLineHeight = 18.0;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _scrollToTarget() {
    if (_scrolled || _target == null) return;
    _scrolled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      // Jump near the line first so it gets built, then bring it into view.
      _scroll.jumpTo(
        (_target! * _estimatedLineHeight).clamp(
          0,
          _scroll.position.maxScrollExtent,
        ),
      );
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final target = _targetKey.currentContext;
        if (target != null && target.mounted) {
          Scrollable.ensureVisible(target, alignment: 0.3);
        }
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    final highlight = Theme.of(
      context,
    ).colorScheme.primaryContainer.withValues(alpha: 0.5);
    return FutureBuilder<String>(
      future: _content,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(child: ErrorCard(error: snapshot.error!));
        }
        final lines = (snapshot.data ?? '').split('\n');
        _target ??= citedLineIndex(lines, widget.location);
        _scrollToTarget();
        return SelectionArea(
          child: ListView.builder(
            controller: _scroll,
            padding: const EdgeInsets.all(16),
            itemCount: lines.length,
            itemBuilder: (context, index) {
              final line = Text(lines[index], style: _style);
              if (index != _target) return line;
              return Container(key: _targetKey, color: highlight, child: line);
            },
          ),
        );
      },
    );
  }
}

/// The line a citation location points at in converted text: `l:N` is a
/// 1-based line, `s:slug` a heading, `p:N` a page or slide marker.
int? citedLineIndex(List<String> lines, String location) {
  if (location.startsWith('l:')) {
    final line = int.tryParse(location.substring(2));
    if (line == null || lines.isEmpty) return null;
    return (line - 1).clamp(0, lines.length - 1);
  }
  if (location.startsWith('s:')) {
    final wanted = _slug(location.substring(2));
    for (var i = 0; i < lines.length; i++) {
      final heading = RegExp(r'^#{1,6}\s+(.*)$').firstMatch(lines[i].trim());
      if (heading != null && _slug(heading.group(1)!) == wanted) return i;
    }
    return null;
  }
  if (location.startsWith('p:')) {
    // From the citation URL: escaped, so it can't break the pattern.
    final page = RegExp.escape(location.substring(2));
    final marker = RegExp(
      '(\\[Page $page\\]|Slide number:\\s*$page\\b)',
      caseSensitive: false,
    );
    for (var i = 0; i < lines.length; i++) {
      if (marker.hasMatch(lines[i])) return i;
    }
  }
  return null;
}

String _slug(String text) => text
    .toLowerCase()
    .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
    .replaceAll(RegExp(r'^-+|-+$'), '');

void showSourceViewer(BuildContext context, SourceViewerRequest request) {
  showDialog<void>(
    context: context,
    builder: (_) => SourceViewerDialog(request: request),
  );
}

void showConvertedSourceViewer(
  BuildContext context,
  String classId,
  SourceFile file,
) {
  showDialog<void>(
    context: context,
    builder: (_) => _ConvertedSourceDialog(classId: classId, file: file),
  );
}

class _ConvertedSourceDialog extends ConsumerWidget {
  const _ConvertedSourceDialog({required this.classId, required this.file});

  final String classId;
  final SourceFile file;

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
                  const Icon(Icons.description_outlined, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      file.originalFilename,
                      style: theme.textTheme.titleSmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => Navigator.pop(context),
                    tooltip: 'Close',
                  ),
                ],
              ),
            ),
            Expanded(
              child: FutureBuilder<String>(
                future: ref
                    .read(apiClientProvider)
                    .getFileConverted(classId, file.id),
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (snapshot.hasError) {
                    return Center(child: ErrorCard(error: snapshot.error!));
                  }
                  return Markdown(
                    data: stripFrontmatter(snapshot.data ?? ''),
                    selectable: true,
                    padding: const EdgeInsets.all(16),
                    styleSheet: MarkdownStyleSheet.fromTheme(theme),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
