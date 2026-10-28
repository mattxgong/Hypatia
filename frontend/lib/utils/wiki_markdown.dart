import '../models/wiki_page.dart';
import 'markdown_math.dart' show standaloneInlineMath;

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

final _displayOpen = RegExp(r'^ {0,3}(\$\$|\\\[)');
// A citation run with an optional sentence-ending mark, at the start of a line
// or making up the rest of one.
final _leadingCites = RegExp(
  '^[ \\t]*($_citePattern(?:[ \\t]*,?[ \\t]*$_citePattern)*)[ \\t]*[.,;]?[ \\t]*',
);
final _trailingMark = RegExp(r'[ \t]*([:,;.])?[ \t]*$');

/// Moves the citation for a display equation into the sentence that
/// introduces it ("the loss is[source](…):"). Written after the equation, it
/// would render as a stray "¹." paragraph, and on the equation's own line it
/// would turn the equation into inline math.
String attachEquationCitations(String content) {
  final lines = content.split('\n');
  int? lead; // The last prose line, which introduces the next equation.
  var inFence = false;
  var i = 0;
  while (i < lines.length) {
    final line = lines[i];
    if (line.trimLeft().startsWith('```')) {
      inFence = !inFence;
      lead = null;
    } else if (!inFence &&
        (_displayOpen.hasMatch(line) || standaloneInlineMath.hasMatch(line))) {
      final end = _displayEnd(lines, i);
      if (end != null) {
        final (last, closeAt) = end;
        final tail = lines[last].substring(closeAt);
        if (tail.trim().isNotEmpty) {
          final m = _leadingCites.firstMatch(tail);
          if (m == null || m.end != tail.length) {
            lead = i; // Text after the closer: a paragraph, not an equation.
            i++;
            continue;
          }
          if (lead != null) {
            lines[lead] = _insertBeforeMark(lines[lead], m[1]!);
            lines[last] = lines[last].substring(0, closeAt);
          }
        } else if (lead != null) {
          var next = last + 1;
          while (next < lines.length && lines[next].trim().isEmpty) {
            next++;
          }
          final m = next < lines.length
              ? _leadingCites.firstMatch(lines[next])
              : null;
          if (m != null) {
            lines[lead] = _insertBeforeMark(lines[lead], m[1]!);
            final rest = lines[next].substring(m.end);
            if (rest.isEmpty) {
              lines.removeAt(next);
            } else {
              lines[next] = rest;
            }
          }
        }
        i = last + 1;
        continue;
      }
    } else if (!inFence && line.trim().isNotEmpty) {
      final t = line.trimLeft();
      lead = t.startsWith('#') || t.startsWith('|') ? null : i;
    }
    i++;
  }
  return lines.join('\n');
}

/// The line and column where the display math opened on line [start] closes,
/// or null if it doesn't close.
(int, int)? _displayEnd(List<String> lines, int start) {
  if (standaloneInlineMath.hasMatch(lines[start])) {
    return (start, lines[start].length);
  }
  final open = _displayOpen.firstMatch(lines[start])!;
  final close = open[1] == r'$$' ? r'$$' : r'\]';
  final first = lines[start].indexOf(close, open.end);
  if (first >= 0) return (start, first + close.length);
  for (var j = start + 1; j < lines.length; j++) {
    final at = lines[j].indexOf(close);
    if (at >= 0) return (j, at + close.length);
  }
  return null;
}

String _insertBeforeMark(String line, String cites) {
  final m = _trailingMark.firstMatch(line)!;
  return '${line.substring(0, m.start)} $cites${m[1] ?? ''}';
}

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
