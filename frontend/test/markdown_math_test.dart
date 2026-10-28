import 'package:flutter/material.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/utils/markdown_math.dart';

Widget _render(String data) => MaterialApp(
  home: Scaffold(
    body: Markdown(
      data: data,
      extensionSet: mathExtensionSet,
      builders: mathBuilders,
    ),
  ),
);

void main() {
  testWidgets('renders inline and display math', (tester) async {
    await tester.pumpWidget(
      _render(
        r'The model \(p(y \mid x; w)\) is normalized.'
        '\n\n'
        r'$$'
        '\n'
        r'\sum_{y} p(y \mid x) = 1'
        '\n'
        r'$$',
      ),
    );

    expect(find.byType(Math), findsNWidgets(2));
    expect(find.textContaining('is normalized.'), findsOneWidget);
    expect(find.textContaining(r'\mid'), findsNothing);
  });

  testWidgets('renders the forms the wiki prompt asks for', (tester) async {
    await tester.pumpWidget(
      _render(
        r'**Sigmoid:** \( \sigma(x) = \frac{1}{1 + e^{-x}} \) squashes.'
        '\n\n'
        r'\[ f(x) = \begin{cases} x & x > 0 \\ \alpha (e^x - 1) & x \le 0 \end{cases} \]',
      ),
    );

    final maths = tester.widgetList<Math>(find.byType(Math)).toList();
    expect(maths, hasLength(2));
    expect(maths.map((m) => m.parseError), everyElement(isNull));

    // The `\\` row break reaches TeX intact rather than as a markdown escape.
    final nodes = md.Document(
      extensionSet: mathExtensionSet,
    ).parseLines([r'\[ \begin{cases} a & b \\ c & d \end{cases} \]']);
    expect(nodes.single.textContent, contains(r'b \\ c'));
  });

  testWidgets('leaves prices as text', (tester) async {
    await tester.pumpWidget(_render(r'It costs $5 or $10.'));

    expect(find.byType(Math), findsNothing);
    expect(find.textContaining(r'$5 or $10'), findsOneWidget);
  });

  testWidgets('inline math sits on the text baseline', (tester) async {
    await tester.pumpWidget(_render(r'Let \(x_i\) be the input.'));

    final spans = <WidgetSpan>[];
    for (final text in tester.widgetList<RichText>(find.byType(RichText))) {
      text.text.visitChildren((span) {
        if (span is WidgetSpan) spans.add(span);
        return true;
      });
    }

    expect(spans, hasLength(1));
    expect(spans.single.alignment, PlaceholderAlignment.baseline);
    expect(spans.single.baseline, TextBaseline.alphabetic);
  });

  testWidgets('tall inline math on consecutive lines does not overlap', (
    tester,
  ) async {
    const frac = '\$\\dfrac{a^2}{b_i}\$';
    await tester.pumpWidget(_render('one $frac  \ntwo $frac  \nthree'));

    final rects = tester
        .widgetList(find.byType(Math))
        .map((m) => tester.getRect(find.byWidget(m)))
        .toList();
    expect(rects, hasLength(2));
    expect(rects[1].top - rects[0].bottom, greaterThanOrEqualTo(4));
  });

  testWidgets('short inline math keeps the regular line height', (
    tester,
  ) async {
    double paragraphHeight() => tester
        .getSize(
          find.byWidgetPredicate(
            (w) => w is RichText && w.text.toPlainText().contains('three'),
          ),
        )
        .height;

    await tester.pumpWidget(_render('one  \ntwo  \nthree'));
    final plain = paragraphHeight();
    await tester.pumpWidget(_render('a \$x\$ one  \na \$y\$ two  \nthree'));

    expect(paragraphHeight(), plain);
  });
}
