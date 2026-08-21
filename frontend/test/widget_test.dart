import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/main.dart';
import 'package:frontend/providers/theme_provider.dart';

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  ProviderScope wrapWithProviders(Widget child) {
    return ProviderScope(
      overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
      child: child,
    );
  }

  testWidgets('App renders without throwing', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(wrapWithProviders(const HypatiaApp()));
    await tester.pump();

    expect(find.byType(Scaffold), findsOneWidget);
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
