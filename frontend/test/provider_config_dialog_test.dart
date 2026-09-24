import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/sidebar/provider_config_dialog.dart';

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(baseUrl: 'http://test');

  String? updatedProvider;
  String? updatedOpenAiKey;
  String? testedModel;
  String? testedApiKey;

  @override
  Future<({bool valid, String? error})> testConnection(
    String provider, {
    String? apiKey,
    String? model,
    String? ollamaBaseUrl,
  }) async {
    testedModel = model;
    testedApiKey = apiKey;
    return (valid: false, error: 'The model "$model" is not available.');
  }

  @override
  Future<Map<String, dynamic>> getSettings() async => {
    'llm_provider': 'copilot',
    'llm_model': 'gpt-5.4',
    'llm_models': {'copilot': 'gpt-5.4', 'openai': 'gpt-test'},
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

  testWidgets('shows the model saved for this provider', (tester) async {
    await tester.pumpWidget(_app(_FakeApiClient()));
    await tester.pumpAndSettle();

    expect(find.text('gpt-test'), findsOneWidget);
    expect(find.text('gpt-5.4'), findsNothing);
  });

  testWidgets('test connection uses the unsaved model and saved key', (
    tester,
  ) async {
    final apiClient = _FakeApiClient();
    await tester.pumpWidget(_app(apiClient));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Model'),
      'gpt-unsaved',
    );
    await tester.tap(find.text('Test Connection'));
    await tester.pumpAndSettle();

    expect(apiClient.testedModel, 'gpt-unsaved');
    expect(apiClient.testedApiKey, isNull);
    expect(apiClient.updatedProvider, isNull);
    expect(
      find.text('The model "gpt-unsaved" is not available.'),
      findsOneWidget,
    );
  });
}
