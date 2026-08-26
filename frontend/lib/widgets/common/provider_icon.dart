import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

class ProviderIcon extends StatelessWidget {
  const ProviderIcon({super.key, required this.providerId, this.size = 20});

  final String providerId;
  final double size;

  @override
  Widget build(BuildContext context) {
    final assetName = _assetFor(providerId);
    final color = _colorFor(providerId, context);

    return SvgPicture.asset(
      assetName,
      width: size,
      height: size,
      colorFilter: ColorFilter.mode(color, BlendMode.srcIn),
    );
  }

  String _assetFor(String id) {
    switch (id) {
      case 'copilot':
      case 'copilot-ollama':
        return 'assets/icons/copilot.svg';
      case 'anthropic':
        return 'assets/icons/anthropic.svg';
      case 'openai':
        return 'assets/icons/openai.svg';
      case 'ollama':
        return 'assets/icons/ollama.svg';
      default:
        return 'assets/icons/openai.svg';
    }
  }

  Color _colorFor(String id, BuildContext context) {
    final theme = Theme.of(context);
    switch (id) {
      case 'copilot':
        return theme.brightness == Brightness.dark
            ? const Color(0xFF79C0FF)
            : const Color(0xFF24292F);
      case 'anthropic':
        return const Color(0xFFD97706);
      case 'openai':
        return const Color(0xFF10A37F);
      case 'ollama':
        return theme.brightness == Brightness.dark
            ? Colors.white70
            : const Color(0xFF333333);
      case 'copilot-ollama':
        return theme.colorScheme.secondary;
      default:
        return theme.colorScheme.onSurface;
    }
  }
}
