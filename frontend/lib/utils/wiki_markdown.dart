import '../models/wiki_page.dart';

final _nonSlug = RegExp(r'[^a-z0-9]+');
final _edgeDashes = RegExp(r'^-+|-+$');

String _slugify(String s) =>
    s.toLowerCase().replaceAll(_nonSlug, '-').replaceAll(_edgeDashes, '');

String _pathStem(String path) =>
    path.split('/').last.replaceFirst(RegExp(r'\.md$'), '');

/// Finds the page a `[[target]]` link means, by filename stem or by title.
WikiPageSummary? findWikiPage(String target, List<WikiPageSummary> pages) {
  if (pages.any((p) => p.path == target)) {
    return pages.firstWhere((p) => p.path == target);
  }
  final slug = _slugify(target);
  for (final p in pages) {
    if (_slugify(_pathStem(p.path)) == slug) return p;
  }
  for (final p in pages) {
    if (_slugify(p.title) == slug) return p;
  }
  return null;
}

final _wikiLink = RegExp(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]');

String _escapeLinkText(String text) =>
    text.replaceAllMapped(RegExp(r'[\[\]]'), (m) => '\\${m[0]}');

/// Turns `[[slug]]` / `[[slug|label]]` into `wiki://` links labelled with the
/// target page's title, falling back to the slug with its dashes removed.
String resolveWikiLinks(String content, List<WikiPageSummary> pages) {
  return content.replaceAllMapped(_wikiLink, (m) {
    final target = m[1]!.trim();
    final page = findWikiPage(target, pages);
    final label =
        m[2]?.trim() ??
        page?.title ??
        target.replaceAll(RegExp(r'[-_]+'), ' ').trim();
    final href = Uri.encodeComponent(page?.path ?? target);
    return '[${_escapeLinkText(label)}](wiki://$href)';
  });
}

const _superscriptDigits = '⁰¹²³⁴⁵⁶⁷⁸⁹';

String _superscript(int n) =>
    n.toString().split('').map((d) => _superscriptDigits[int.parse(d)]).join();

const _citePattern = r'\[[^\]]*\]\((hypatia://cite\?[^)\s]*)\)';
final _citeOne = RegExp(_citePattern);
// Adjacent citations (optionally comma-separated) collapse into one group,
// and the space before the group is dropped so the numbers hug the text.
final _citeRun = RegExp(
  '[ \\t]*$_citePattern(?:[ \\t]*,?[ \\t]*$_citePattern)*',
);

/// Renders `hypatia://cite` links as numbered superscripts (AMA style) and
/// appends a numbered References list. Repeat citations of the same file
/// location reuse their number.
///
/// [fileNames] maps file IDs to display names for citations that use an ID.
String numberCitations(
  String content, {
  Map<String, String> fileNames = const {},
}) {
  final numbers = <String, int>{};
  final refs = <String>[];

  final body = content.replaceAllMapped(_citeRun, (run) {
    final group = <int>{};
    for (final m in _citeOne.allMatches(run[0]!)) {
      final href = m[1]!;
      final uri = Uri.tryParse(href);
      if (uri == null) continue;
      final key = _citationKey(uri);
      group.add(
        numbers.putIfAbsent(key, () {
          refs.add(href);
          return refs.length;
        }),
      );
    }
    if (group.isEmpty) return run[0]!;
    final sorted = group.toList()..sort();
    return sorted.map((n) => '[${_superscript(n)}](${refs[n - 1]})').join(',');
  });

  if (refs.isEmpty) return content;
  final list = [
    for (var i = 0; i < refs.length; i++)
      '${i + 1}. [${_escapeLinkText(describeCitation(Uri.parse(refs[i]), fileNames: fileNames))}](${refs[i]})',
  ];
  return '${body.trimRight()}\n\n---\n\n#### References\n\n${list.join('\n')}\n';
}

String _citationKey(Uri uri) {
  final q = uri.queryParameters;
  return [
    q['file'],
    q['page'],
    q['t'],
    q['section'],
    q['line'],
  ].map((v) => v ?? '').join('|');
}

/// Human-readable reference text, e.g. "notes.pdf, p. 5" or "lecture.mp4, 5:42".
String describeCitation(Uri uri, {Map<String, String> fileNames = const {}}) {
  final q = uri.queryParameters;
  final file = q['file'] ?? 'Source';
  final name = fileNames[file] ?? file;
  if (q['page'] case final page?) return '$name, p. $page';
  if (q['t'] case final t?) return '$name, ${_formatSeconds(t)}';
  if (q['section'] case final section?) {
    return '$name, § ${section.replaceAll(RegExp(r'[-_]+'), ' ')}';
  }
  if (q['line'] case final line?) return '$name, line $line';
  return name;
}

/// The source viewer's location code for a citation: `p:5`, `t:342`,
/// `s:heading`, `l:42`, or empty for the whole file.
String citationLocation(Uri uri) {
  final q = uri.queryParameters;
  if (q['page'] case final page?) return 'p:$page';
  if (q['t'] case final t?) return 't:$t';
  if (q['section'] case final section?) return 's:$section';
  if (q['line'] case final line?) return 'l:$line';
  return q['loc'] ?? '';
}

String _formatSeconds(String raw) {
  final total = int.tryParse(raw);
  if (total == null) return raw;
  final h = total ~/ 3600;
  final m = (total % 3600) ~/ 60;
  final s = (total % 60).toString().padLeft(2, '0');
  return h > 0 ? '$h:${m.toString().padLeft(2, '0')}:$s' : '$m:$s';
}
