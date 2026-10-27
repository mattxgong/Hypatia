import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/app.dart';
import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/backend_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/services/backend_launcher.dart';

class _EmptyClassListNotifier extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [];
}

class _FakeLauncher extends BackendLauncher {
  final statuses = StreamController<BackendStatus>.broadcast();
  BackendStatus current = BackendStatus.starting;

  @override
  BackendStatus get status => current;
  @override
  Stream<BackendStatus> get onStatusChange => statuses.stream;
  @override
  String? get apiToken => 'launch-token';
  @override
  String get baseUrl => 'http://127.0.0.1:8001';

  void emit(BackendStatus status) {
    current = status;
    statuses.add(status);
  }
}

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  testWidgets('App renders without throwing', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          classListProvider.overrideWith(() => _EmptyClassListNotifier()),
        ],
        child: const HypatiaApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(Scaffold), findsOneWidget);
    expect(find.text('Welcome to Hypatia'), findsOneWidget);
    expect(find.byTooltip('About Hypatia'), findsOneWidget);
  });

  testWidgets('Startup screen shows until the backend is ready', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final launcher = _FakeLauncher();
    final container = ProviderContainer(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        backendLauncherProvider.overrideWithValue(launcher),
        classListProvider.overrideWith(() => _EmptyClassListNotifier()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const HypatiaApp(),
      ),
    );
    await tester.pump();

    expect(find.text('Start the backend'), findsOneWidget);
    expect(find.text('Welcome to Hypatia'), findsNothing);
    expect(find.byType(MaterialApp), findsOneWidget);

    launcher.emit(BackendStatus.ready);
    await tester.pumpAndSettle();

    expect(find.text('Welcome to Hypatia'), findsOneWidget);
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(container.read(backendApiTokenProvider), 'launch-token');
    expect(container.read(backendBaseUrlProvider), 'http://127.0.0.1:8001');
  });

  testWidgets('Theme toggle persists preference', (tester) async {
    SharedPreferences.setMockInitialValues({'hypatia_theme_mode': 'dark'});
    prefs = await SharedPreferences.getInstance();

    final container = ProviderContainer(
      overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
    );
    addTearDown(container.dispose);

    final notifier = container.read(themeModeProvider.notifier);
    expect(container.read(themeModeProvider), ThemeMode.dark);

    await notifier.toggle();
    expect(container.read(themeModeProvider), ThemeMode.light);
    expect(prefs.getString('hypatia_theme_mode'), 'light');

    await notifier.toggle();
    expect(container.read(themeModeProvider), ThemeMode.dark);
    expect(prefs.getString('hypatia_theme_mode'), 'dark');
  });

  testWidgets('Theme loads saved preference on build', (tester) async {
    SharedPreferences.setMockInitialValues({'hypatia_theme_mode': 'light'});
    prefs = await SharedPreferences.getInstance();

    final container = ProviderContainer(
      overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
    );
    addTearDown(container.dispose);

    expect(container.read(themeModeProvider), ThemeMode.light);
  });
}
