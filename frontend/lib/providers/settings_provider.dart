import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_client.dart';

final llmProviderSettingProvider =
    AsyncNotifierProvider<LlmProviderSettingNotifier, String>(
      LlmProviderSettingNotifier.new,
    );

class LlmProviderSettingNotifier extends AsyncNotifier<String> {
  @override
  Future<String> build() async {
    final apiClient = ref.read(apiClientProvider);
    final data = await apiClient.getSettings();
    return data['llm_provider'] as String? ?? 'copilot';
  }

  Future<void> setProvider(String provider) async {
    final apiClient = ref.read(apiClientProvider);
    await apiClient.updateSettings(llmProvider: provider);
    state = AsyncData(provider);
  }
}

final fullSettingsProvider =
    AsyncNotifierProvider<FullSettingsNotifier, Map<String, dynamic>>(
      FullSettingsNotifier.new,
    );

class FullSettingsNotifier extends AsyncNotifier<Map<String, dynamic>> {
  @override
  Future<Map<String, dynamic>> build() async {
    final apiClient = ref.read(apiClientProvider);
    return apiClient.getSettings();
  }

  Future<void> updateFields({
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
    final apiClient = ref.read(apiClientProvider);
    final result = await apiClient.updateSettings(
      llmProvider: llmProvider,
      llmModel: llmModel,
      llmTemperature: llmTemperature,
      llmMaxTokens: llmMaxTokens,
      anthropicApiKey: anthropicApiKey,
      openaiApiKey: openaiApiKey,
      githubToken: githubToken,
      ollamaBaseUrl: ollamaBaseUrl,
      whisperModelSize: whisperModelSize,
      whisperDevice: whisperDevice,
    );
    state = AsyncData(result);
  }

  Future<void> refresh() async {
    final apiClient = ref.read(apiClientProvider);
    state = AsyncData(await apiClient.getSettings());
  }
}

final ollamaModelsProvider = FutureProvider<List<String>>((ref) async {
  final apiClient = ref.read(apiClientProvider);
  try {
    return await apiClient.getOllamaModels();
  } catch (_) {
    return [];
  }
});

class LlmConnectionStatus {
  const LlmConnectionStatus({
    required this.provider,
    required this.model,
    required this.connected,
    this.error,
  });

  final String provider;
  final String? model;
  final bool connected;
  final String? error;
}

/// Tests the saved provider configuration; re-runs whenever it changes.
final llmConnectionStatusProvider = FutureProvider<LlmConnectionStatus>((
  ref,
) async {
  final config = await ref.watch(
    fullSettingsProvider.selectAsync(
      (s) => (
        provider: s['llm_provider'] as String? ?? 'copilot',
        model: s['llm_model'] as String?,
        baseUrl: s['ollama_base_url'] as String?,
        keys: (s['anthropic_api_key'], s['openai_api_key'], s['github_token']),
      ),
    ),
  );
  try {
    final result = await ref
        .read(apiClientProvider)
        .testConnection(config.provider);
    return LlmConnectionStatus(
      provider: config.provider,
      model: config.model,
      connected: result.valid,
      error: result.error,
    );
  } on ApiException catch (e) {
    return LlmConnectionStatus(
      provider: config.provider,
      model: config.model,
      connected: false,
      error: e.detail,
    );
  }
});
