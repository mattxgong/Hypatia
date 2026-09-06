import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/sidebar/provider_config_dialog.dart';

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(baseUrl: 'http://test');

  String? updatedProvider;
  String? updatedOpenAiKey;

  @override
  Future<Map<String, dynamic>> getSettings() async => {
    'llm_provider': 'openai',
    'llm_model': 'gpt-test',
    'openai_api_key': 'sk-a...7890',
  };

  @override
  Future<Map<String, dynamic>> updateSettings({
    String? llmProvider,
    String? llmModel,
    double? llmTemperature,
    int? llmMaxTokens,
    String? anthropicApiKey,
    String? openaiApiKey,
    String? githubToken,
    String? ollamaBaseUrl,
    String? whisperModelSize,
    String? whisperDevice,
  }) async {
    updatedProvider = llmProvider;
    updatedOpenAiKey = openaiApiKey;
    return getSettings();
  }
}

Widget _app(_FakeApiClient apiClient) {
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(apiClient)],
    child: const MaterialApp(
      home: Scaffold(
        body: ProviderConfigDialog(
          providerId: 'openai',
          activateProvider: true,
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('saving does not submit the masked stored key', (tester) async {
    final apiClient = _FakeApiClient();
    await tester.pumpWidget(_app(apiClient));
    await tester.pumpAndSettle();

    expect(find.text('A saved key is configured'), findsOneWidget);
    expect(find.text('sk-a...7890'), findsNothing);

    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(apiClient.updatedProvider, 'openai');
    expect(apiClient.updatedOpenAiKey, isNull);
  });

  testWidgets('clear saved key sends an explicit empty value', (tester) async {
    final apiClient = _FakeApiClient();
    await tester.pumpWidget(_app(apiClient));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Clear saved key'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(apiClient.updatedOpenAiKey, '');
  });
}
