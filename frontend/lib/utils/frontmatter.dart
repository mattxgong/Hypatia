final _frontmatter = RegExp(
  r'^\uFEFF?---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)',
);
final _leadingBlankLines = RegExp(r'^(?:[ \t]*\r?\n)+');

/// Removes a leading YAML frontmatter block, which Markdown would otherwise
/// render as a setext heading made of the raw metadata.
String stripFrontmatter(String content) =>
    content.replaceFirst(_frontmatter, '').replaceFirst(_leadingBlankLines, '');
