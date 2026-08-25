import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/widgets/chat_panel/chat_panel.dart';
import 'package:frontend/widgets/chat_panel/command_input.dart';

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  Widget wrapWithProviders(Widget child, {String? classId}) {
    return ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        if (classId != null)
          currentClassIdProvider.overrideWith((ref) => classId),
      ],
      child: MaterialApp(
        home: Scaffold(body: SizedBox(width: 350, child: child)),
      ),
    );
  }

  testWidgets('Chat panel shows starter cards when empty', (tester) async {
    // No classId → shows StarterCards without triggering API-backed chat provider
    await tester.pumpWidget(wrapWithProviders(const ChatPanel()));
    await tester.pumpAndSettle();

    expect(find.text('Ask about my wiki'), findsOneWidget);
    expect(find.text('Summarize a topic'), findsOneWidget);
    expect(find.text('Add files'), findsOneWidget);
  });

  testWidgets('Chat panel shows header with new chat button', (tester) async {
    await tester.pumpWidget(wrapWithProviders(const ChatPanel()));
    await tester.pumpAndSettle();

    expect(find.text('Chat'), findsOneWidget);
    expect(find.byTooltip('New conversation'), findsOneWidget);
  });

  testWidgets('Command input shows autocomplete on / prefix', (tester) async {
    await tester.pumpWidget(
      wrapWithProviders(const CommandInput(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    await tester.enterText(textField, '/');
    await tester.pump();

    expect(find.text('/ask'), findsOneWidget);
    expect(find.text('/summarize'), findsOneWidget);
    expect(find.text('/rebuild'), findsOneWidget);
  });

  testWidgets('Command input filters autocomplete options', (tester) async {
    await tester.pumpWidget(
      wrapWithProviders(const CommandInput(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    await tester.enterText(textField, '/re');
    await tester.pump();

    expect(find.text('/remove'), findsOneWidget);
    expect(find.text('/rebuild'), findsOneWidget);
    expect(find.text('/ask'), findsNothing);
  });

  testWidgets('Command input hides autocomplete after space', (tester) async {
    await tester.pumpWidget(
      wrapWithProviders(const CommandInput(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    await tester.enterText(textField, '/ask ');
    await tester.pump();

    expect(find.text('/ask'), findsNothing);
  });
}
