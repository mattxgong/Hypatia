import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/chat_provider.dart';
import '../../providers/class_provider.dart';
import '../../utils/shortcuts.dart';
import '../common/error_card.dart';
import '../sidebar/add_file_button.dart';
import 'command_input.dart';
import 'message_bubble.dart';
import 'starter_cards.dart';

class ChatPanel extends ConsumerWidget {
  const ChatPanel({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    ref.watch(chatConnectionProvider);
    final theme = Theme.of(context);

    return Material(
      color: theme.colorScheme.surfaceContainerLowest,
      child: Column(
        children: [
          _ChatHeader(
            onClearHistory: classId == null
                ? null
                : () => _confirmClearHistory(context, ref, classId),
          ),
          Expanded(child: _ChatBody(classId: classId)),
          const CommandInput(),
        ],
      ),
    );
  }
}

Future<void> _confirmClearHistory(
  BuildContext context,
  WidgetRef ref,
  String classId,
) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Clear chat history?'),
      content: const Text(
        "This permanently deletes this class's chat messages. "
        'Your wiki, sources and study material are not affected.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('Clear history'),
        ),
      ],
    ),
  );
  if (confirmed == true) {
    await ref.read(chatMessagesProvider(classId).notifier).clearHistory();
  }
}

class _ChatBody extends ConsumerWidget {
  const _ChatBody({required this.classId});

  final String? classId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (classId == null) return _buildStarterCards(context, ref);

    final messagesAsync = ref.watch(chatMessagesProvider(classId!));
    // Only whether something is streaming: the text itself is watched by the
    // streaming bubble, so each chunk doesn't rebuild every message.
    final streaming = ref.watch(
      chatStreamingContentProvider(classId!).select((s) => s.isNotEmpty),
    );

    return messagesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: ErrorCard(
          error: e,
          onRetry: () => ref.invalidate(chatMessagesProvider(classId!)),
        ),
      ),
      data: (messages) {
        if (messages.isEmpty && !streaming) {
          return _buildStarterCards(context, ref);
        }

        final itemCount = messages.length + (streaming ? 1 : 0);
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          reverse: true,
          itemCount: itemCount,
          itemBuilder: (context, index) {
            if (index == 0 && streaming) {
              return _StreamingBubble(classId: classId!);
            }
            final msgIndex = streaming ? index - 1 : index;
            final message = messages[messages.length - 1 - msgIndex];
            return MessageBubble(message: message);
          },
        );
      },
    );
  }

  Widget _buildStarterCards(BuildContext context, WidgetRef ref) {
    return StarterCards(
      onAsk: () => ref.read(chatInputFocusRequestProvider.notifier).state++,
      onSummarize: () =>
          ref.read(chatInputProvider.notifier).state = '/summarize ',
      onAddFiles: () => pickAndUploadFiles(context, ref),
    );
  }
}

class _StreamingBubble extends ConsumerWidget {
  const _StreamingBubble({required this.classId});

  final String classId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final content = ref.watch(chatStreamingContentProvider(classId));
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
  const _ChatHeader({required this.onClearHistory});

  final VoidCallback? onClearHistory;

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
            constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
          ),
          IconButton(
            icon: const Icon(Icons.delete_sweep_outlined, size: 18),
            onPressed: onClearHistory,
            tooltip: 'Clear chat history',
            iconSize: 18,
            constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
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
    _CmdEntry(
      '/flashcards [topic]',
      'Make a flashcard deck from the whole wiki or one topic. Uses your AI '
          'model when it is reachable, otherwise builds the deck offline.',
      '/flashcards hidden markov models',
    ),
    _CmdEntry(
      '/quiz [topic]',
      'Make a practice quiz from the whole wiki or one topic, with AI when '
          'available.',
      '/quiz',
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
              _shortcutRow('$shortcutModifierLabel+K', 'Focus search bar'),
              _shortcutRow('$shortcutModifierLabel+N', 'Create a new class'),
              _shortcutRow('$shortcutModifierLabel+B', 'Toggle sidebar'),
              _shortcutRow('$shortcutModifierLabel+J', 'Toggle chat panel'),
              _shortcutRow('Enter', 'Send (Shift+Enter: new line)'),
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
