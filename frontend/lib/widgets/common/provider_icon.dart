import 'package:flutter/material.dart';

class ProviderIcon extends StatelessWidget {
  const ProviderIcon({super.key, required this.providerId, this.size = 20});

  final String providerId;
  final double size;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = _iconFor(providerId, context);
    return Icon(icon, size: size, color: color);
  }

  (IconData, Color?) _iconFor(String id, BuildContext context) {
    final theme = Theme.of(context);
    switch (id) {
      case 'copilot':
        return (Icons.auto_awesome, theme.colorScheme.primary);
      case 'anthropic':
        return (Icons.psychology, const Color(0xFFD97706));
      case 'openai':
        return (Icons.hub, const Color(0xFF10A37F));
      case 'ollama':
        return (Icons.computer, theme.colorScheme.tertiary);
      case 'copilot-ollama':
        return (Icons.device_hub, theme.colorScheme.secondary);
      default:
        return (Icons.smart_toy, null);
    }
  }
}
