import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:markdown/markdown.dart' as md;

const _inlineTag = 'math-inline';
const _blockTag = 'math-block';

/// GitHub-flavored markdown plus TeX math: `\(..\)` / `$..$` inline and
/// `\[..\]` / `$$..$$` display.
final mathExtensionSet = md.ExtensionSet(
  [MathBlockSyntax(), ...md.ExtensionSet.gitHubFlavored.blockSyntaxes],
  [MathInlineSyntax(), ...md.ExtensionSet.gitHubFlavored.inlineSyntaxes],
);

final mathBuilders = <String, MarkdownElementBuilder>{
  _inlineTag: _MathBuilder(block: false),
  _blockTag: _MathBuilder(block: true),
};

class MathInlineSyntax extends md.InlineSyntax {
  MathInlineSyntax()
    : super(
        r'\$\$([\s\S]+?)\$\$'
        r'|\\\(([\s\S]+?)\\\)'
        r'|\\\[([\s\S]+?)\\\]'
        // A lone `$` pair must hug its content, so prices like "$5 or $10" stay text.
        r'|(?<![\\\w$])\$(?=\S)([^$\n]+?)(?<=\S)\$(?![\w$])',
      );

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final display = match[1] ?? match[3];
    final tex = display ?? match[2] ?? match[4]!;
    final element = md.Element.text(_inlineTag, tex);
    if (display != null) element.attributes['display'] = 'true';
    parser.addNode(element);
    return true;
  }
}

/// A `$$` or `\[` line opens display math that runs until the matching closer.
class MathBlockSyntax extends md.BlockSyntax {
  static final _open = RegExp(r'^ {0,3}(\$\$|\\\[)(.*)$');

  @override
  RegExp get pattern => _open;

  @override
  bool canParse(md.BlockParser parser) {
    final match = _open.firstMatch(parser.current.content);
    if (match == null) return false;
    final close = _closerFor(match[1]!);
    final end = match[2]!.indexOf(close);
    // `$$x$$ and more` on one line is inline math inside a paragraph.
    return end < 0 || match[2]!.substring(end + close.length).trim().isEmpty;
  }

  @override
  md.Node parse(md.BlockParser parser) {
    final match = _open.firstMatch(parser.current.content)!;
    final close = _closerFor(match[1]!);
    final rest = match[2]!;
    final lines = <String>[];
    parser.advance();

    final end = rest.indexOf(close);
    if (end >= 0) {
      lines.add(rest.substring(0, end));
    } else {
      lines.add(rest);
      while (!parser.isDone) {
        final line = parser.current.content;
        parser.advance();
        final i = line.indexOf(close);
        if (i >= 0) {
          lines.add(line.substring(0, i));
          break;
        }
        lines.add(line);
      }
    }
    return md.Element.text(_blockTag, lines.join('\n').trim());
  }

  static String _closerFor(String opener) => opener == r'$$' ? r'$$' : r'\]';
}

class _MathBuilder extends MarkdownElementBuilder {
  _MathBuilder({required this.block});

  final bool block;

  @override
  bool isBlockElement() => block;

  @override
  Widget? visitElementAfterWithContext(
    BuildContext context,
    md.Element element,
    TextStyle? preferredStyle,
    TextStyle? parentStyle,
  ) {
    final tex = element.textContent.trim();
    if (tex.isEmpty) return null;
    final display = block || element.attributes['display'] == 'true';
    final style = parentStyle ?? DefaultTextStyle.of(context).style;
    final math = Math.tex(
      tex,
      mathStyle: display ? MathStyle.display : MathStyle.text,
      textStyle: style,
      onErrorFallback: (_) => Text(display ? '\\[$tex\\]' : '\\($tex\\)'),
    );

    if (block) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: math,
        ),
      );
    }
    // A Text wrapper lets the markdown builder merge the math into the
    // surrounding paragraph instead of breaking the line around it.
    return Text.rich(
      TextSpan(
        children: [
          WidgetSpan(
            alignment: PlaceholderAlignment.baseline,
            baseline: TextBaseline.alphabetic,
            child: math,
          ),
        ],
      ),
    );
  }
}
