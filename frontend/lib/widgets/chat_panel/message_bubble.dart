import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/chat_message.dart';
import '../../providers/wiki_provider.dart';
import '../common/wiki_markdown.dart';

/// The wiki pages an answer drew on (`metadata_json['pages']`), as
/// `(path, title)` pairs.
List<(String, String)> consultedPages(ChatMessage message) {
  final pages = message.metadataJson?['pages'];
  if (pages is! List) return const [];
  return [
    for (final p in pages)
      if (p is Map && p['path'] is String)
        (p['path'] as String, (p['title'] as String?) ?? p['path'] as String),
  ];
}

class MessageBubble extends ConsumerWidget {
  const MessageBubble({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isUser = message.role == ChatRole.user;
    final pages = isUser ? const <(String, String)>[] : consultedPages(message);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: isUser
            ? MainAxisAlignment.end
            : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser)
            Padding(
              padding: const EdgeInsets.only(right: 8, top: 4),
              child: CircleAvatar(
                radius: 14,
                backgroundColor: theme.colorScheme.primaryContainer,
                child: Icon(
                  Icons.auto_awesome,
                  size: 14,
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
            ),
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: isUser
                    ? theme.colorScheme.primaryContainer
                    : theme.colorScheme.surfaceContainerHigh,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (isUser)
                    // Selectable, like the replies, so a question can be
                    // copied and asked again.
                    SelectableText(
                      message.content,
                      style: theme.textTheme.bodyMedium,
                    )
                  else
                    WikiMarkdown(
                      data: message.content,
                      scrollable: false,
                      styleSheet: MarkdownStyleSheet.fromTheme(
                        theme,
                      ).copyWith(p: theme.textTheme.bodyMedium),
                    ),
                  if (pages.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      'From',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        for (final (path, title) in pages)
                          ActionChip(
                            avatar: const Icon(
                              Icons.article_outlined,
                              size: 16,
                            ),
                            label: Text(title),
                            tooltip: 'Open $title',
                            visualDensity: VisualDensity.compact,
                            onPressed: () =>
                                ref
                                        .read(
                                          currentWikiPagePathProvider.notifier,
                                        )
                                        .state =
                                    path,
                          ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
          if (isUser) const SizedBox(width: 36),
        ],
      ),
    );
  }
}
