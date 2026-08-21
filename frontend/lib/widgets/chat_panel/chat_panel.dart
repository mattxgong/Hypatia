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
    final messages = classId != null
        ? ref.watch(chatMessagesProvider(classId))
        : null;
    final theme = Theme.of(context);

    return Material(
      color: theme.colorScheme.surfaceContainerLowest,
      child: Column(
        children: [
          _ChatHeader(
            onNewChat: () {
              if (classId != null) {
                ref.read(chatMessagesProvider(classId).notifier).clear();
              }
            },
          ),
          Expanded(
            child: messages == null || messages.isEmpty
                ? const StarterCards()
                : ListView.builder(
                    padding: const EdgeInsets.all(12),
                    reverse: true,
                    itemCount: messages.length,
                    itemBuilder: (context, index) {
                      final message = messages[messages.length - 1 - index];
                      return MessageBubble(message: message);
                    },
                  ),
          ),
          const CommandInput(),
        ],
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
