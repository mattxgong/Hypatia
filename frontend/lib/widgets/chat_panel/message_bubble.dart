import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import '../../models/chat_message.dart';

class MessageBubble extends StatelessWidget {
  const MessageBubble({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isUser = message.role == ChatRole.user;

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
              child: isUser
                  ? Text(message.content, style: theme.textTheme.bodyMedium)
                  : MarkdownBody(
                      data: message.content,
                      selectable: true,
                      styleSheet: MarkdownStyleSheet.fromTheme(
                        theme,
                      ).copyWith(p: theme.textTheme.bodyMedium),
                    ),
            ),
          ),
          if (isUser) const SizedBox(width: 36),
        ],
      ),
    );
  }
}
