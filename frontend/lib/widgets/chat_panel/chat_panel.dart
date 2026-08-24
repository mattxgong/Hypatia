import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/chat_provider.dart';
import '../../providers/class_provider.dart';
import 'command_input.dart';
import 'message_bubble.dart';
import 'starter_cards.dart';

class ChatPanel extends ConsumerWidget {
  const ChatPanel({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    final theme = Theme.of(context);

    return Material(
      color: theme.colorScheme.surfaceContainerLowest,
      child: Column(
        children: [
          _ChatHeader(
            onNewChat: () {
              if (classId != null) {
                ref.read(chatMessagesProvider(classId).notifier).clearHistory();
              }
            },
          ),
          Expanded(child: _ChatBody(classId: classId)),
          const CommandInput(),
        ],
      ),
    );
  }
}

class _ChatBody extends ConsumerWidget {
  const _ChatBody({required this.classId});

  final String? classId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (classId == null) return const StarterCards();

    final messagesAsync = ref.watch(chatMessagesProvider(classId!));
    final streamingContent = ref.watch(chatStreamingContentProvider);

    return messagesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error loading chat: $e')),
      data: (messages) {
        if (messages.isEmpty && streamingContent.isEmpty) {
          return const StarterCards();
        }

        final itemCount =
            messages.length + (streamingContent.isNotEmpty ? 1 : 0);
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          reverse: true,
          itemCount: itemCount,
          itemBuilder: (context, index) {
            if (index == 0 && streamingContent.isNotEmpty) {
              return _StreamingBubble(content: streamingContent);
            }
            final msgIndex = streamingContent.isNotEmpty ? index - 1 : index;
            final message = messages[messages.length - 1 - msgIndex];
            return MessageBubble(message: message);
          },
        );
      },
    );
  }
}

class _StreamingBubble extends StatelessWidget {
  const _StreamingBubble({required this.content});

  final String content;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(content, style: theme.textTheme.bodyMedium),
      ),
    );
  }
}

class _ChatHeader extends StatelessWidget {
  const _ChatHeader({required this.onNewChat});

  final VoidCallback onNewChat;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      height: 40,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: theme.dividerColor)),
      ),
      child: Row(
        children: [
          Text('Chat', style: theme.textTheme.titleSmall),
          const Spacer(),
          IconButton(
            icon: const Icon(Icons.add, size: 18),
            onPressed: onNewChat,
            tooltip: 'New conversation',
            iconSize: 18,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
          ),
        ],
      ),
    );
  }
}
