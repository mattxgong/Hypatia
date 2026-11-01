import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../config/theme.dart';

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

  Color _colorFor(String id, BuildContext context) =>
      ProviderBrandColors.of(id, Theme.of(context));
}
