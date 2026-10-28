import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/chat_message.dart';
import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/models/source_file.dart';
import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/providers/backend_provider.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/search_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/upload_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/services/backend_launcher.dart';
import 'package:frontend/widgets/backend_gate.dart';
import 'package:frontend/widgets/chat_panel/message_bubble.dart';
import 'package:frontend/widgets/sidebar/class_dropdown.dart';
import 'package:frontend/widgets/sidebar/search_bar.dart';
import 'package:frontend/widgets/sidebar/wiki_tree.dart';
import 'package:frontend/widgets/source_viewer/source_viewer.dart';

const _classId = 'class-1';

class _FakeApi extends ApiClient {
  _FakeApi() : super(baseUrl: 'http://test');

  Object? createError;
  final progressCalls = <(int, int)>[];

  @override
  Future<HypatiaClass> createClass({
    required String name,
    String? description,
  }) async {
    if (createError != null) throw createError!;
    return HypatiaClass(
      id: 'new',
      name: name,
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    );
  }

  @override
  Future<List<Map<String, dynamic>>> uploadFiles(
    String classId,
    List<String> filePaths, {
    void Function(int sent, int total)? onProgress,
    CancelToken? cancelToken,
  }) async {
    // Two 10-byte files: report the first one done, then all of it.
    onProgress?.call(12, 20);
    return [];
  }

  @override
  Future<List<SourceFile>> listFiles(String classId) async => [];
}

class _Classes extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [
    HypatiaClass(
      id: _classId,
      name: 'Biology',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    ),
  ];
}

void main() {
  late SharedPreferences prefs;
  late _FakeApi api;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    api = _FakeApi();
  });

  Widget wrap(Widget child) => ProviderScope(
    overrides: [
      sharedPreferencesProvider.overrideWithValue(prefs),
      apiClientProvider.overrideWithValue(api),
      currentClassIdProvider.overrideWith((ref) => _classId),
      classListProvider.overrideWith(_Classes.new),
      wikiTreeProvider(_classId).overrideWith(
        (ref) async => [
          const WikiPageSummary(
            id: 'p1',
            path: 'pages/concepts/entropy.md',
            title: 'Entropy',
            category: WikiCategory.concept,
          ),
        ],
      ),
    ],
    child: MaterialApp(home: Scaffold(body: child)),
  );

  testWidgets('the search box empties when its query is cleared elsewhere', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(const SidebarSearchBar()));
    await tester.enterText(find.byType(TextField), 'entropy');
    await tester.pump(const Duration(milliseconds: 400));

    final container = ProviderScope.containerOf(
      tester.element(find.byType(SidebarSearchBar)),
    );
    expect(container.read(searchQueryProvider), 'entropy');
    container.read(searchQueryProvider.notifier).state = '';
    await tester.pump();

    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      '',
    );
  });

  testWidgets('new class lives in its own menu, not the class list', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(const ClassDropdown()));
    await tester.pumpAndSettle();

    final dropdown = tester.widget<DropdownButton<String>>(
      find.byType(DropdownButton<String>),
    );
    expect(dropdown.items!.map((i) => i.value), [_classId]);

    await tester.tap(find.byTooltip('Add a class'));
    await tester.pumpAndSettle();
    expect(find.text('New class…'), findsOneWidget);
    expect(find.text('Import from backup…'), findsOneWidget);
  });

  testWidgets('creating a class with a taken name says so', (tester) async {
    api.createError = ApiException(
      detail: 'A class named "Biology" already exists',
      statusCode: 409,
    );
    await tester.pumpWidget(wrap(const ClassDropdown()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Add a class'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('New class…'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).first, 'Biology');
    await tester.tap(find.text('Create'));
    await tester.pumpAndSettle();

    expect(find.text('A class named "Biology" already exists'), findsOneWidget);
    expect(find.text('New Class'), findsOneWidget); // the dialog stays open
  });

  test('upload progress counts finished files', () async {
    final dir = await Directory.systemTemp.createTemp('upload');
    addTearDown(() => dir.delete(recursive: true));
    final paths = [
      for (final name in ['a.md', 'b.md'])
        (File('${dir.path}/$name')..writeAsStringSync('0123456789')).path,
    ];
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        currentClassIdProvider.overrideWith((ref) => _classId),
        fileListProvider(_classId).overrideWith((ref) async => []),
      ],
    );
    addTearDown(container.dispose);
    final states = <UploadState>[];
    container.listen(uploadProgressProvider, (_, s) => states.add(s));

    await container.read(uploadProgressProvider.notifier).uploadFiles(paths);

    final during = states.firstWhere((s) => s.status == UploadStatus.uploading);
    expect(
      states.any((s) => s.filesDone == 1 && s.currentFileName == 'b.md'),
      isTrue,
      reason: '$during',
    );
    expect(
      container.read(uploadProgressProvider).status,
      UploadStatus.complete,
    );
  });

  test('an upload that throws something unexpected ends in error', () async {
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        currentClassIdProvider.overrideWith((ref) => _classId),
      ],
    );
    addTearDown(container.dispose);

    await container.read(uploadProgressProvider.notifier).uploadFiles([
      '/no/such/file.md',
    ]);

    expect(container.read(uploadProgressProvider).status, UploadStatus.error);
  });

  test('citations find their line, section or page in converted text', () {
    final lines = [
      '# Notes',
      '**[Page 1]**',
      'intro',
      '## Hidden Markov Models',
      '<!-- Slide number: 3 -->',
      'text',
    ];
    expect(citedLineIndex(lines, 'l:3'), 2);
    expect(citedLineIndex(lines, 'l:999'), 5);
    expect(citedLineIndex(lines, 's:hidden-markov-models'), 3);
    expect(citedLineIndex(lines, 'p:1'), 1);
    expect(citedLineIndex(lines, 'p:3'), 4);
    expect(citedLineIndex(lines, 'p:('), isNull);
    expect(citedLineIndex(lines, 't:30'), isNull);
  });

  testWidgets('an answer links the pages it drew on', (tester) async {
    final message = ChatMessage(
      id: 'm1',
      classId: _classId,
      role: ChatRole.assistant,
      content: 'Entropy measures uncertainty.',
      metadataJson: {
        'pages': [
          {'path': 'pages/concepts/entropy.md', 'title': 'Entropy'},
        ],
      },
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    );
    await tester.pumpWidget(wrap(MessageBubble(message: message)));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ActionChip, 'Entropy'));
    final container = ProviderScope.containerOf(
      tester.element(find.byType(MessageBubble)),
    );
    expect(
      container.read(currentWikiPagePathProvider),
      'pages/concepts/entropy.md',
    );
  });

  testWidgets('startup shows which step it is on', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [backendStatusProvider.overrideWith(_SettingUp.new)],
        child: const MaterialApp(home: BackendGate(child: Text('app'))),
      ),
    );
    await tester.pump();

    expect(find.text('app'), findsNothing);
    expect(find.text('Set up the backend environment'), findsOneWidget);
    expect(find.textContaining('first launch'), findsOneWidget);
    // Find Python is done; starting the backend is still to come.
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    expect(find.byIcon(Icons.radio_button_unchecked), findsOneWidget);
  });

  testWidgets('wiki tree sections collapse', (tester) async {
    await tester.pumpWidget(wrap(const WikiTree()));
    await tester.pumpAndSettle();
    expect(find.text('Entropy'), findsOneWidget);

    await tester.tap(find.text('Concepts (1)'));
    await tester.pumpAndSettle();
    expect(find.text('Entropy'), findsNothing);
  });
}

class _SettingUp extends BackendStatusNotifier {
  @override
  BackendStatus build() => BackendStatus.settingUpEnvironment;
}
