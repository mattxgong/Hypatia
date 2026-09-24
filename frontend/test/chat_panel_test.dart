import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/chat_message.dart';
import 'package:frontend/providers/chat_provider.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/chat_panel/chat_panel.dart';
import 'package:frontend/widgets/chat_panel/command_input.dart';
import 'package:frontend/widgets/chat_panel/message_bubble.dart';

class _PreviewApiClient extends ApiClient {
  _PreviewApiClient() : super(baseUrl: 'http://test');

  bool confirmed = false;

  @override
  Future<Map<String, dynamic>> rebuildWiki(
    String classId, {
    bool confirm = false,
  }) async {
    confirmed = confirmed || confirm;
    return {
      'pages_to_create': <String>[],
      'pages_to_delete': ['pages/concept/hidden-markov-models.md'],
      'pages_preserved_user_edited': ['pages/concept/mine.md'],
      'pages_preserved_synthesis': <String>[],
      'source_file_count': 2,
      'estimated_tokens': 1200,
    };
  }
}

class _RecordingChatNotifier extends ChatMessagesNotifier {
  final sent = <String>[];

  @override
  Future<List<ChatMessage>> build(String arg) async => [];

  @override
  void sendMessage(String content) => sent.add(content);
}

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

  testWidgets('Starter cards populate and focus the command input', (
    tester,
  ) async {
    await tester.pumpWidget(wrapWithProviders(const ChatPanel()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Summarize a topic'));
    await tester.pump();

    final input = tester.widget<TextField>(find.byType(TextField));
    expect(input.controller!.text, '/summarize ');
    expect(input.focusNode!.hasFocus, isTrue);
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

  testWidgets('Assistant messages render math, wiki links, and citations', (
    tester,
  ) async {
    final message = ChatMessage(
      id: 'm1',
      classId: 'class-1',
      role: ChatRole.assistant,
      content:
          r'See [[log-linear-models]] where \(p(y \mid x)\) is normalized '
          '[source](hypatia://cite?file=crf.pdf&page=2).',
      createdAt: DateTime(2024),
      updatedAt: DateTime(2024),
    );
    await tester.pumpWidget(wrapWithProviders(MessageBubble(message: message)));
    await tester.pumpAndSettle();

    expect(find.byType(Math), findsOneWidget);
    expect(find.textContaining('log linear models'), findsOneWidget);
    expect(find.textContaining('crf.pdf, p. 2'), findsOneWidget);
    expect(find.textContaining('[source]'), findsNothing);
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

  testWidgets('/rebuild asks for confirmation and can be cancelled', (
    tester,
  ) async {
    final api = _PreviewApiClient();
    final chat = _RecordingChatNotifier();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          currentClassIdProvider.overrideWith((ref) => 'class-1'),
          apiClientProvider.overrideWithValue(api),
          chatMessagesProvider.overrideWith(() => chat),
        ],
        child: const MaterialApp(home: Scaffold(body: CommandInput())),
      ),
    );

    await tester.enterText(find.byType(TextField), '/rebuild');
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();

    expect(find.text('Rebuild the wiki?'), findsOneWidget);
    expect(find.textContaining('hidden markov models'), findsOneWidget);
    expect(find.textContaining('1 page you edited'), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(chat.sent, isEmpty);
    expect(api.confirmed, isFalse);

    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Rebuild'));
    await tester.pumpAndSettle();
    expect(chat.sent, ['/rebuild']);
  });
}
