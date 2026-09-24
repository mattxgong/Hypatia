import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/source_file.dart';
import '../../models/wiki_page.dart';
import '../../providers/class_provider.dart';
import '../../providers/file_provider.dart';
import '../../providers/wiki_provider.dart';
import '../../utils/markdown_math.dart';
import '../../utils/wiki_markdown.dart';
import '../wiki_viewer/wiki_viewer.dart'
    show SourceViewerRequest, sourceViewerRequestProvider;

/// Markdown for LLM-written wiki content: TeX math, `[[wiki-links]]` shown by
/// page title, and `hypatia://cite` links as numbered citations. Tapping a link
/// opens the wiki page or the cited source location.
class WikiMarkdown extends ConsumerWidget {
  const WikiMarkdown({
    super.key,
    required this.data,
    required this.styleSheet,
    this.scrollable = true,
  });

  final String data;
  final MarkdownStyleSheet styleSheet;

  /// Whether to build a scrolling [Markdown] or a sized [MarkdownBody].
  final bool scrollable;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    final pages = classId == null
        ? const <WikiPageSummary>[]
        : ref.watch(wikiTreeProvider(classId)).valueOrNull ?? const [];
    final files = classId == null
        ? const <SourceFile>[]
        : ref.watch(fileListProvider(classId)).valueOrNull ?? const [];
    final rendered = numberCitations(
      resolveWikiLinks(data, pages),
      fileNames: {for (final f in files) f.id: f.originalFilename},
    );

    void onTap(String text, String? href, String title) =>
        _handleLink(ref, href, pages);

    // SelectionArea rather than `selectable`, which cannot host inline math.
    return SelectionArea(
      child: scrollable
          ? Markdown(
              data: rendered,
              extensionSet: mathExtensionSet,
              builders: mathBuilders,
              onTapLink: onTap,
              styleSheet: styleSheet,
            )
          : MarkdownBody(
              data: rendered,
              extensionSet: mathExtensionSet,
              builders: mathBuilders,
              onTapLink: onTap,
              styleSheet: styleSheet,
            ),
    );
  }

  static void _handleLink(
    WidgetRef ref,
    String? href,
    List<WikiPageSummary> pages,
  ) {
    if (href == null) return;

    if (href.startsWith('wiki://')) {
      final target = Uri.decodeComponent(href.substring('wiki://'.length));
      final match = findWikiPage(target, pages);
      if (match != null) {
        ref.read(currentWikiPagePathProvider.notifier).state = match.path;
      }
    } else if (href.startsWith('hypatia://cite')) {
      final uri = Uri.parse(href);
      ref
          .read(sourceViewerRequestProvider.notifier)
          .state = SourceViewerRequest(
        fileRef: uri.queryParameters['file'] ?? '',
        location: citationLocation(uri),
      );
    } else if (href.startsWith('http://') || href.startsWith('https://')) {
      launchUrl(Uri.parse(href), mode: LaunchMode.externalApplication);
    }
  }
}
