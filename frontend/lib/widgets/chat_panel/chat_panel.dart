import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/chat_provider.dart';
import '../../providers/class_provider.dart';
import '../common/error_card.dart';
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
      error: (e, _) => Center(
        child: ErrorCard(
          error: e,
          onRetry: () => ref.invalidate(chatMessagesProvider(classId!)),
        ),
      ),
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
            icon: const Icon(Icons.help_outline, size: 18),
            onPressed: () => _showCommandReference(context),
            tooltip: 'Command reference',
            iconSize: 18,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
          ),
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

  void _showCommandReference(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => const _CommandReferenceDialog(),
    );
  }
}

class _CommandReferenceDialog extends StatelessWidget {
  const _CommandReferenceDialog();

  static const _commands = [
    _CmdEntry(
      '/ask <query>',
      'Ask a question about your wiki. The LLM answers with citations from '
          'your source material.',
      'What is gradient descent?',
    ),
    _CmdEntry(
      '/summarize <topic>',
      'Generate a new wiki summary page on a given topic from your sources.',
      '/summarize key concepts from lecture 3',
    ),
    _CmdEntry(
      '/remove <filename>',
      'Remove a source file and clean up all wiki pages derived from it.',
      '/remove lecture1.pdf',
    ),
    _CmdEntry(
      '/lint',
      'Check the wiki for contradictions and structural issues.',
      '/lint',
    ),
    _CmdEntry(
      '/rebuild',
      'Regenerate the entire wiki from all sources. This is a long-running '
          'operation with progress updates.',
      '/rebuild',
    ),
    _CmdEntry(
      '/export',
      'Export the wiki as a collection of markdown files.',
      '/export',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Command Reference'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Type a message without a / prefix to ask a question. '
                'Use these commands for specific actions:',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: 16),
              ..._commands.map(
                (cmd) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        cmd.syntax,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontFamily: 'monospace',
                          color: theme.colorScheme.primary,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(cmd.description, style: theme.textTheme.bodySmall),
                      if (cmd.example.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          'Example: ${cmd.example}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontStyle: FontStyle.italic,
                            color: theme.colorScheme.onSurface.withValues(
                              alpha: 0.5,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const Divider(),
              const SizedBox(height: 4),
              Text('Keyboard shortcuts', style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              _shortcutRow('Ctrl+K', 'Focus search bar'),
              _shortcutRow('Ctrl+N', 'Create a new class'),
              _shortcutRow('Ctrl+B', 'Toggle sidebar'),
              _shortcutRow('Ctrl+J', 'Toggle chat panel'),
              _shortcutRow('Escape', 'Clear search / close dialog'),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _shortcutRow(String key, String description) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(
              key,
              style: const TextStyle(
                fontFamily: 'monospace',
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Text(description, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}

class _CmdEntry {
  const _CmdEntry(this.syntax, this.description, this.example);
  final String syntax;
  final String description;
  final String example;
}
