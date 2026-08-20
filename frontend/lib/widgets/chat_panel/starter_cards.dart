import 'package:flutter/material.dart';

class StarterCards extends StatelessWidget {
  const StarterCards({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _StarterCard(
            icon: Icons.question_answer_outlined,
            title: 'Ask about my wiki',
            subtitle: 'Query your knowledge base',
            onTap: () {},
          ),
          const SizedBox(height: 12),
          _StarterCard(
            icon: Icons.summarize_outlined,
            title: 'Summarize a topic',
            subtitle: 'Generate a new wiki page',
            onTap: () {},
          ),
          const SizedBox(height: 12),
          _StarterCard(
            icon: Icons.upload_file_outlined,
            title: 'Add files',
            subtitle: 'Upload source material',
            onTap: () {},
          ),
        ],
      ),
    );
  }
}

class _StarterCard extends StatelessWidget {
  const _StarterCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(icon, size: 24, color: theme.colorScheme.primary),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: theme.textTheme.bodyMedium),
                    Text(
                      subtitle,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.6,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.chevron_right,
                size: 18,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
