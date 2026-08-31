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
