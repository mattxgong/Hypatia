import 'package:flutter/material.dart';
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
