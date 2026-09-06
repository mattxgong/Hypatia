import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/app.dart';
import 'package:frontend/models/chat_message.dart';
import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/services/websocket_service.dart';

const _classId = 'integration-class';

class _WorkflowClassListNotifier extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [];

  @override
  Future<HypatiaClass> create({
    required String name,
    String? description,
  }) async {
    final now = DateTime(2026, 9, 5);
    final created = HypatiaClass(
      id: _classId,
      name: name,
      description: description,
      createdAt: now,
      updatedAt: now,
    );
    state = AsyncData([created]);
    return created;
  }
}

class _WorkflowApiClient extends ApiClient {
  _WorkflowApiClient() : super(baseUrl: 'http://integration.test');

  @override
  Future<List<ChatMessage>> getChatHistory(
    String classId, {
    int limit = 50,
    int offset = 0,
  }) async => [];

  @override
  Future<Map<String, dynamic>> getSettings() async => {
    'llm_provider': 'copilot',
  };
}

class _WorkflowWebSocketService extends WebSocketService {
  _WorkflowWebSocketService({required super.apiClient});

  @override
  Stream<ChatWsChunk> get onChunk => const Stream.empty();

  @override
  Stream<ChatWsComplete> get onComplete => const Stream.empty();

  @override
  Stream<ChatWsProgress> get onProgress => const Stream.empty();

  @override
  Stream<ChatWsError> get onError => const Stream.empty();

  @override
  Future<void> connect(String classId) async {}

  @override
  void dispose() {}
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('creates a class and starts a wiki command', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();
    final apiClient = _WorkflowApiClient();
    final webSocketService = _WorkflowWebSocketService(apiClient: apiClient);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(preferences),
          apiClientProvider.overrideWithValue(apiClient),
          webSocketServiceProvider.overrideWithValue(webSocketService),
          classListProvider.overrideWith(_WorkflowClassListNotifier.new),
          fileListProvider(_classId).overrideWith((ref) async => []),
          wikiTreeProvider(_classId).overrideWith((ref) async => []),
        ],
        child: const HypatiaShell(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Welcome to Hypatia'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Create Class'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).first, 'Biology 101');
    await tester.enterText(
      find.byType(TextFormField).last,
      'Cellular biology notes',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();

    expect(find.text('Biology 101'), findsWidgets);
    expect(find.text('Select a wiki page from the sidebar'), findsOneWidget);
    expect(find.text('Summarize a topic'), findsOneWidget);

    await tester.tap(find.text('Summarize a topic'));
    await tester.pump();

    final commandInput = tester.widget<TextField>(
      find.byWidgetPredicate(
        (widget) =>
            widget is TextField &&
            widget.decoration?.hintText == 'Ask anything, /command...',
      ),
    );
    expect(commandInput.controller?.text, '/summarize ');
    expect(commandInput.focusNode?.hasFocus, isTrue);
  });
}
