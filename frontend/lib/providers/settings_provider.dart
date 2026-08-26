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
