/// Integration test scaffolding for Hypatia (Task 8.2c).
///
/// This is a smoke test that verifies the app launches without crashing.
/// Additional integration tests should be added as features stabilize.
///
/// Run with: flutter test integration_test/
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:frontend/main.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('App launch', () {
    testWidgets('HypatiaApp widget renders', (tester) async {
      await tester.pumpWidget(const HypatiaApp());
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(MaterialApp), findsOneWidget);
    });
  });
}
