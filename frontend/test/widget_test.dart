import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('App renders without throwing', (WidgetTester tester) async {
    await tester.pumpWidget(const HypatiaApp());
    await tester.pump();

    expect(find.byType(Scaffold), findsOneWidget);
  });
}
