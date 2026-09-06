import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/widgets/common/hypatia_about_button.dart';

void main() {
  testWidgets('About dialog exposes compiled dependency licenses', (
    tester,
  ) async {
    LicenseRegistry.addLicense(() async* {
      yield const LicenseEntryWithLineBreaks([
        'Hypatia Test Dependency',
      ], 'Test dependency license text.');
    });

    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: HypatiaAboutButton())),
    );

    await tester.tap(find.byTooltip('About Hypatia'));
    await tester.pumpAndSettle();

    expect(find.text('Hypatia'), findsOneWidget);
    expect(find.textContaining('Copyright 2026 Matthew Gong'), findsOneWidget);

    await tester.tap(find.text('View licenses'));
    await tester.pumpAndSettle();

    expect(find.text('Hypatia Test Dependency'), findsOneWidget);

    await tester.tap(find.text('Hypatia Test Dependency'));
    await tester.pumpAndSettle();

    expect(find.text('Test dependency license text.'), findsOneWidget);
  });
}
