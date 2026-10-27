import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/providers/settings_provider.dart';
import 'package:frontend/widgets/common/provider_setup_prompt.dart';

class _FakeSettings extends FullSettingsNotifier {
  _FakeSettings(this.settings);

  final Map<String, dynamic> settings;

  @override
  Future<Map<String, dynamic>> build() async => settings;
}

Widget _app(Map<String, dynamic> settings) => ProviderScope(
  overrides: [fullSettingsProvider.overrideWith(() => _FakeSettings(settings))],
  child: const MaterialApp(
    home: ProviderSetupPrompt(child: Scaffold(body: Text('home'))),
  ),
);

void main() {
  testWidgets('asks for an Anthropic key when none is saved', (tester) async {
    await tester.pumpWidget(
      _app({'llm_provider': 'anthropic', 'anthropic_api_key': null}),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Paste an Anthropic API key'), findsOneWidget);
  });

  testWidgets('stays out of the way once a key is saved', (tester) async {
    await tester.pumpWidget(
      _app({'llm_provider': 'anthropic', 'anthropic_api_key': 'sk-a...xyz'}),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Paste an Anthropic API key'), findsNothing);
    expect(find.text('home'), findsOneWidget);
  });

  testWidgets('stays out of the way for other providers', (tester) async {
    await tester.pumpWidget(
      _app({'llm_provider': 'ollama', 'anthropic_api_key': null}),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Paste an Anthropic API key'), findsNothing);
  });
}
