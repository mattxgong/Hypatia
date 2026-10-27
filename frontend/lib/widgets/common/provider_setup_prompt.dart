import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/settings_provider.dart';
import '../sidebar/provider_config_dialog.dart';

/// Set once the first-run prompt has been shown, so it opens once per launch.
final providerSetupPromptShownProvider = StateProvider<bool>((ref) => false);

/// Opens the provider dialog on first run: Claude (Anthropic) is the default
/// provider, and nothing works until it has an API key.
class ProviderSetupPrompt extends ConsumerStatefulWidget {
  const ProviderSetupPrompt({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<ProviderSetupPrompt> createState() =>
      _ProviderSetupPromptState();
}

class _ProviderSetupPromptState extends ConsumerState<ProviderSetupPrompt> {
  @override
  void initState() {
    super.initState();
    ref.listenManual(fullSettingsProvider, (_, next) {
      final settings = next.valueOrNull;
      if (settings == null || !needsAnthropicKey(settings)) return;
      if (ref.read(providerSetupPromptShownProvider)) return;
      ref.read(providerSetupPromptShownProvider.notifier).state = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_prompt()));
    }, fireImmediately: true);
  }

  Future<void> _prompt() async {
    if (!mounted) return;
    final saved = await showProviderConfigDialog(
      context,
      'anthropic',
      activateProvider: true,
      intro:
          'Hypatia uses Claude to build your wiki and answer questions. '
          'Paste an Anthropic API key to get started, or close this and pick '
          'another provider from the sidebar.',
    );
    if (saved) {
      ref.invalidate(llmProviderSettingProvider);
      ref.invalidate(fullSettingsProvider);
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// Whether the configured provider is Anthropic with no API key saved.
bool needsAnthropicKey(Map<String, dynamic> settings) =>
    (settings['llm_provider'] as String? ?? 'anthropic') == 'anthropic' &&
    (settings['anthropic_api_key'] as String?)?.isNotEmpty != true;
