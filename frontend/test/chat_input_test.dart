import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/chat_message.dart';
import 'package:frontend/providers/chat_provider.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/widgets/chat_panel/chat_panel.dart';
import 'package:frontend/widgets/chat_panel/command_input.dart';

class _RecordingChat extends ChatMessagesNotifier {
  final sent = <String>[];
  var stopped = 0;
  var cleared = 0;

  @override
  Future<List<ChatMessage>> build(String arg) async => [
    ChatMessage(
      id: 'm1',
      classId: arg,
      role: ChatRole.user,
      content: 'hello',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    ),
  ];

  @override
  bool sendMessage(String content) {
    sent.add(content);
    return true;
  }

  @override
  void stop() => stopped++;

  @override
  Future<void> clearHistory() async => cleared++;
}

void main() {
  late SharedPreferences prefs;
  late _RecordingChat chat;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    chat = _RecordingChat();
  });

  Widget wrap(Widget child, {List<Override> overrides = const []}) =>
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          currentClassIdProvider.overrideWith((ref) => 'class-1'),
          chatMessagesProvider.overrideWith(() => chat),
          chatConnectionProvider.overrideWithValue(null),
          ...overrides,
        ],
        child: MaterialApp(home: Scaffold(body: child)),
      );

  TextField input(WidgetTester tester) =>
      tester.widget<TextField>(find.byType(TextField));

  testWidgets('arrow keys and Enter pick a suggested command', (tester) async {
    await tester.pumpWidget(wrap(const CommandInput()));
    await tester.enterText(find.byType(TextField), '/');
    await tester.pump();
    expect(find.textContaining('Answer from the wiki'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();

    expect(input(tester).controller!.text, '/summarize ');
    expect(chat.sent, isEmpty);
  });

  testWidgets('Enter sends and Shift+Enter starts a new line', (tester) async {
    await tester.pumpWidget(wrap(const CommandInput()));
    await tester.enterText(find.byType(TextField), 'first line');
    await tester.pump();

    await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
    await tester.pump();
    expect(chat.sent, isEmpty);

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(chat.sent, ['first line']);
  });

  testWidgets('Stop replaces Send while an operation runs', (tester) async {
    await tester.pumpWidget(
      wrap(
        const CommandInput(),
        overrides: [
          chatActiveOperationProvider('class-1').overrideWith((ref) => 'op-1'),
        ],
      ),
    );

    expect(find.byTooltip('Send'), findsNothing);
    await tester.tap(find.byTooltip('Stop'));
    expect(chat.stopped, 1);
  });

  testWidgets('clearing chat history asks first', (tester) async {
    await tester.pumpWidget(wrap(const ChatPanel()));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Clear chat history'));
    await tester.pumpAndSettle();
    expect(find.text('Clear chat history?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(chat.cleared, 0);

    await tester.tap(find.byTooltip('Clear chat history'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear history'));
    await tester.pumpAndSettle();
    expect(chat.cleared, 1);
  });
}
