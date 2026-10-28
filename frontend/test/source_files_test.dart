import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/models/source_file.dart';
import 'package:frontend/models/task_status.dart';
import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/task_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/common/activity_status.dart';
import 'package:frontend/widgets/sidebar/wiki_tree.dart';

const _classId = 'class-1';

SourceFile _file(
  String id,
  String name, {
  FileStatus status = FileStatus.ready,
  String? converted = 'converted.md',
  String? error,
}) => SourceFile(
  id: id,
  classId: _classId,
  originalFilename: name,
  fileType: FileType.pdf,
  fileSizeBytes: 1,
  rawPath: 'raw/$name',
  convertedPath: converted,
  status: status,
  errorMessage: error,
  createdAt: DateTime(2026),
  updatedAt: DateTime(2026),
);

class _FakeApi extends ApiClient {
  _FakeApi() : super(baseUrl: 'http://test');

  List<SourceFile> files = [];
  final deleted = <String>[];
  final retried = <String>[];

  @override
  Future<List<SourceFile>> listFiles(String classId) async => files;

  @override
  Future<void> deleteFile(String classId, String fileId) async {
    deleted.add(fileId);
    files = files.where((f) => f.id != fileId).toList();
  }

  @override
  Future<SourceFile> retryFile(String classId, String fileId) async {
    retried.add(fileId);
    return files.firstWhere((f) => f.id == fileId);
  }
}

class _NoTasks extends TaskListNotifier {
  _NoTasks(this.tasks);

  final List<TaskStatus> tasks;

  @override
  TaskListState build() => TaskListState(tasks: tasks);

  @override
  Future<void> fetchTasks() async {}
}

void main() {
  late _FakeApi api;

  setUp(() => api = _FakeApi());

  Widget wrap(Widget child, {List<TaskStatus> tasks = const []}) =>
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          currentClassIdProvider.overrideWith((ref) => _classId),
          wikiTreeProvider(
            _classId,
          ).overrideWith((ref) async => const <WikiPageSummary>[]),
          taskListProvider.overrideWith(() => _NoTasks(tasks)),
        ],
        child: MaterialApp(
          home: Scaffold(body: SourceFileEvents(child: child)),
        ),
      );

  Future<void> rightClick(WidgetTester tester, String text) async {
    await tester.tap(find.text(text), buttons: kSecondaryButton);
    await tester.pumpAndSettle();
  }

  testWidgets('a failed file can be retried from its menu', (tester) async {
    api.files = [
      _file('f1', 'notes.pdf', status: FileStatus.error, converted: null),
    ];
    await tester.pumpWidget(wrap(const WikiTree()));
    await tester.pumpAndSettle();

    await rightClick(tester, 'notes.pdf');
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(api.retried, ['f1']);
  });

  testWidgets('deleting a file asks first', (tester) async {
    api.files = [_file('f1', 'notes.pdf')];
    await tester.pumpWidget(wrap(const WikiTree()));
    await tester.pumpAndSettle();

    await rightClick(tester, 'notes.pdf');
    expect(find.text('Retry'), findsNothing);
    await tester.tap(find.text('Delete…'));
    await tester.pumpAndSettle();
    expect(find.text('Delete notes.pdf?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(api.deleted, isEmpty);

    await rightClick(tester, 'notes.pdf');
    await tester.tap(find.text('Delete…'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();
    expect(api.deleted, ['f1']);
    expect(find.text('Deleted notes.pdf'), findsOneWidget);
  });

  testWidgets('the top bar shows what is running', (tester) async {
    await tester.pumpWidget(
      wrap(
        const ActivityStatus(),
        tasks: [
          const TaskStatus(
            taskId: 't1',
            operation: 'ingest',
            classId: _classId,
            status: 'running',
            progress: 40,
            message: 'Ingesting notes.pdf (part 2/5)',
            createdAt: '2026-10-01T00:00:00Z',
          ),
        ],
      ),
    );
    await tester.pump();

    expect(find.text('Ingesting notes.pdf (part 2/5) · 40%'), findsOneWidget);
  });

  testWidgets('a file that fails while processing is announced', (
    tester,
  ) async {
    api.files = [
      _file('f1', 'notes.pdf', status: FileStatus.pending, converted: null),
    ];
    await tester.pumpWidget(wrap(const WikiTree()));
    // Not pumpAndSettle: the pending file's spinner never stops.
    await tester.pump(const Duration(milliseconds: 100));

    api.files = [
      _file(
        'f1',
        'notes.pdf',
        status: FileStatus.error,
        converted: null,
        error: 'unreadable PDF',
      ),
    ];
    final container = ProviderScope.containerOf(
      tester.element(find.byType(WikiTree)),
    );
    container.invalidate(fileListProvider(_classId));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('notes.pdf failed: unreadable PDF'), findsOneWidget);
    expect(find.widgetWithText(SnackBarAction, 'Retry'), findsOneWidget);
  });
}
