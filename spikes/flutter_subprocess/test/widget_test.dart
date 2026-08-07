import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_subprocess/main.dart';

void main() {
  testWidgets('App renders UI elements', (WidgetTester tester) async {
    await tester.pumpWidget(const SubprocessSpikeApp());

    // The UI renders with initial state
    expect(find.text('Spike 0.5.3: Flutter Subprocess Management'),
        findsOneWidget);
    expect(find.text('Start'), findsOneWidget);
    expect(find.text('Stop'), findsOneWidget);
    expect(find.text('Log Output'), findsOneWidget);

    // Dispose cleanly - pump to flush pending timers from _discoverPython
    await tester.pumpAndSettle(const Duration(seconds: 5));
  });
}
