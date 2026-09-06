import 'package:flutter/material.dart';

class HypatiaAboutButton extends StatelessWidget {
  const HypatiaAboutButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: const Icon(Icons.info_outline, size: 20),
      tooltip: 'About Hypatia',
      visualDensity: VisualDensity.compact,
      onPressed: () => showHypatiaAboutDialog(context),
    );
  }
}

void showHypatiaAboutDialog(BuildContext context) {
  showAboutDialog(
    context: context,
    applicationName: 'Hypatia',
    applicationVersion: '1.0.0',
    applicationIcon: const Icon(Icons.school_outlined, size: 48),
    applicationLegalese:
        'Copyright 2026 Matthew Gong\nLicensed under Apache-2.0',
  );
}
