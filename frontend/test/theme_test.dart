import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/config/theme.dart';

void main() {
  for (final (name, theme) in [
    ('light', HypatiaTheme.lightTheme),
    ('dark', HypatiaTheme.darkTheme),
  ]) {
    testWidgets('$name theme carries the design tokens', (tester) async {
      late HypatiaTokens tokens;
      await tester.pumpWidget(
        MaterialApp(
          theme: theme,
          home: Builder(
            builder: (context) {
              tokens = HypatiaTokens.of(context);
              return const Card(child: Text('card'));
            },
          ),
        ),
      );

      expect(theme.extension<HypatiaTokens>(), isNotNull);
      expect(tokens.textPrimary, theme.colorScheme.onSurface);
      expect(tokens.textMuted, isNot(tokens.textPrimary));
      expect(tokens.danger, theme.colorScheme.error);
      expect(tokens.accentTint.a, lessThan(0.25));
      final shape =
          tester
                  .widget<Material>(
                    find.descendant(
                      of: find.byType(Card),
                      matching: find.byType(Material),
                    ),
                  )
                  .shape!
              as RoundedRectangleBorder;
      expect(shape.borderRadius, HypatiaTokens.corners);
    });
  }

  test('tokens fall back to the scheme when a theme lacks them', () {
    final scheme = ColorScheme.fromSeed(seedColor: Colors.teal);
    expect(HypatiaTokens.from(scheme).hairline, scheme.outlineVariant);
  });

  test('widgets take colors and radii from the theme, not literals', () {
    final offenders = <String>[];
    final literal = RegExp(r'Color\(0x|BorderRadius\.circular\(\d');
    for (final file in Directory('lib').listSync(recursive: true)) {
      if (file is! File || !file.path.endsWith('.dart')) continue;
      if (file.path.replaceAll(r'\', '/').endsWith('config/theme.dart')) {
        continue;
      }
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (literal.hasMatch(lines[i])) offenders.add('${file.path}:${i + 1}');
      }
    }
    expect(
      offenders,
      isEmpty,
      reason: 'Use HypatiaTokens in config/theme.dart',
    );
  });
}
