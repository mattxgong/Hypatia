import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/settings_provider.dart';
import '../common/provider_icon.dart';
import '../sidebar/class_dropdown.dart' show providerOptions;

class ProviderSelector extends ConsumerWidget {
  const ProviderSelector({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final providerAsync = ref.watch(llmProviderSettingProvider);
    final theme = Theme.of(context);

    final currentProvider = providerAsync.valueOrNull ?? 'copilot';

    return DropdownButtonFormField<String>(
      initialValue: currentProvider,
      decoration: InputDecoration(
        labelText: 'AI Provider',
        labelStyle: theme.textTheme.labelSmall,
        contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
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
      onChanged: (value) {
        if (value != null && value != currentProvider) {
          ref.read(llmProviderSettingProvider.notifier).setProvider(value);
        }
      },
    );
  }
}
