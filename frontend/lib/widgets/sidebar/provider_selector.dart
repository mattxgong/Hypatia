import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/settings_provider.dart';
import '../common/provider_icon.dart';
import '../sidebar/class_dropdown.dart' show providerOptions;
import 'provider_config_dialog.dart';

class ProviderSelector extends ConsumerWidget {
  const ProviderSelector({super.key});

  static const _requiresConfig = {
    'anthropic',
    'openai',
    'ollama',
    'copilot-ollama',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final providerAsync = ref.watch(llmProviderSettingProvider);
    final theme = Theme.of(context);

    final currentProvider = providerAsync.valueOrNull ?? 'copilot';

    return Row(
      children: [
        Expanded(
          child: DropdownButtonFormField<String>(
            initialValue: currentProvider,
            decoration: InputDecoration(
              labelText: 'AI Provider',
              labelStyle: theme.textTheme.labelSmall,
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 10,
                vertical: 8,
              ),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide.none,
              ),
              filled: true,
              fillColor: theme.colorScheme.surfaceContainerHigh,
              isDense: true,
            ),
            isExpanded: true,
            items: providerOptions
                .map(
                  (p) => DropdownMenuItem<String>(
                    value: p.id,
                    child: Row(
                      children: [
                        ProviderIcon(providerId: p.id, size: 16),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            p.label,
                            style: theme.textTheme.bodySmall,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
                .toList(),
            onChanged: (value) async {
              if (value != null && value != currentProvider) {
                if (_requiresConfig.contains(value)) {
                  final saved = await showProviderConfigDialog(
                    context,
                    value,
                    activateProvider: true,
                  );
                  if (saved) {
                    ref.invalidate(llmProviderSettingProvider);
                    ref.invalidate(fullSettingsProvider);
                  }
                } else {
                  await ref
                      .read(llmProviderSettingProvider.notifier)
                      .setProvider(value);
                  ref.invalidate(fullSettingsProvider);
                }
              }
            },
          ),
        ),
        const SizedBox(width: 4),
        const ConnectionStatusIndicator(),
        IconButton(
          icon: const Icon(Icons.settings, size: 18),
          onPressed: () => showProviderConfigDialog(context, currentProvider),
          tooltip: 'Configure provider',
          iconSize: 18,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
        ),
      ],
    );
  }
}

class ConnectionStatusIndicator extends ConsumerWidget {
  const ConnectionStatusIndicator({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(llmConnectionStatusProvider);

    final Widget icon;
    final String tooltip;
    if (status.isLoading) {
      icon = const SizedBox(
        width: 14,
        height: 14,
        child: CircularProgressIndicator(strokeWidth: 2),
      );
      tooltip = 'Checking AI connection...';
    } else {
      final value = status.valueOrNull;
      final label = providerOptions
          .where((p) => p.id == value?.provider)
          .map((p) => p.label)
          .firstOrNull;
      if (value != null && value.connected) {
        icon = const Icon(Icons.check_circle, color: Colors.green, size: 18);
        final model = value.model;
        tooltip =
            'Connected to ${label ?? value.provider}'
            '${model != null && model.isNotEmpty ? ' ($model)' : ''}. '
            'Click to re-check.';
      } else {
        icon = const Icon(Icons.error, color: Colors.red, size: 18);
        final reason = value?.error ?? 'Could not reach the Hypatia backend.';
        tooltip = 'Not connected: $reason\nClick to re-check.';
      }
    }

    return IconButton(
      icon: icon,
      onPressed: status.isLoading
          ? null
          : () => ref.invalidate(llmConnectionStatusProvider),
      tooltip: tooltip,
      padding: EdgeInsets.zero,
      constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
    );
  }
}
