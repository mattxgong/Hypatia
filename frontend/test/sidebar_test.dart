import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/models/source_file.dart';
import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/widgets/sidebar/sidebar.dart';

final _mockClasses = [
  HypatiaClass(
    id: 'class-1',
    name: 'Machine Learning',
    createdAt: DateTime(2024),
    updatedAt: DateTime(2024),
  ),
];

final _mockPages = <WikiPageSummary>[
  const WikiPageSummary(
    id: '1',
    path: 'concepts/neural-networks',
    title: 'Neural Networks',
    category: WikiCategory.concept,
  ),
  const WikiPageSummary(
    id: '2',
    path: 'concepts/backpropagation',
    title: 'Backpropagation',
    category: WikiCategory.concept,
  ),
  const WikiPageSummary(
    id: '3',
    path: 'entities/geoffrey-hinton',
    title: 'Geoffrey Hinton',
    category: WikiCategory.entity,
  ),
  const WikiPageSummary(
    id: '4',
    path: 'source-summaries/lecture-1',
    title: 'Lecture 1',
    category: WikiCategory.sourceSummary,
  ),
];

final _mockFiles = <SourceFile>[
  SourceFile(
    id: 'f1',
    classId: 'class-1',
    originalFilename: 'lecture1.pdf',
    fileType: FileType.pdf,
    fileSizeBytes: 1024,
    rawPath: 'raw/lecture1.pdf',
    status: FileStatus.ready,
    createdAt: DateTime(2024),
    updatedAt: DateTime(2024),
  ),
];

class _MockClassListNotifier extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => _mockClasses;
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
        classListProvider.overrideWith(() => _MockClassListNotifier()),
        if (classId != null)
          currentClassIdProvider.overrideWith((ref) => classId),
        if (classId != null)
          wikiTreeProvider(classId).overrideWith((ref) async => _mockPages),
        if (classId != null)
          fileListProvider(classId).overrideWith((ref) async => _mockFiles),
      ],
      child: MaterialApp(
        home: Scaffold(body: SizedBox(width: 250, child: child)),
      ),
    );
  }

  void setLargeTestSurface(WidgetTester tester) {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets('Sidebar renders class dropdown and search bar', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Machine Learning'), findsOneWidget);
    expect(find.byType(TextField), findsWidgets);
    expect(find.text('Search wiki...'), findsOneWidget);
  });

  testWidgets('Sidebar shows wiki tree categories', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Concepts'), findsOneWidget);
    expect(find.textContaining('Source Summaries'), findsOneWidget);
    expect(find.textContaining('Entities'), findsOneWidget);
    expect(find.textContaining('Source Files'), findsOneWidget);
  });

  testWidgets('Wiki tree shows pages under categories', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Neural Networks'), findsOneWidget);
    expect(find.text('Backpropagation'), findsOneWidget);
    expect(find.text('Geoffrey Hinton'), findsOneWidget);
  });

  testWidgets('Sidebar shows Add Files button', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Add Files'), findsOneWidget);
  });

  testWidgets('Sidebar shows theme toggle', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.byTooltip('Toggle theme'), findsOneWidget);
  });
}
