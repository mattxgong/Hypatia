import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/chat_message.dart';
import '../../providers/chat_provider.dart';
import '../../providers/class_provider.dart';

const _commands = [
  '/ask',
  '/summarize',
  '/remove',
  '/lint',
  '/rebuild',
  '/export',
];

class CommandInput extends ConsumerStatefulWidget {
  const CommandInput({super.key});

  @override
  ConsumerState<CommandInput> createState() => _CommandInputState();
}

class _CommandInputState extends ConsumerState<CommandInput> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  bool _showCommands = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onTextChanged);
  }

  void _onTextChanged() {
    final text = _controller.text;
    final shouldShow = text.startsWith('/') && !text.contains(' ');
    if (shouldShow != _showCommands) {
      setState(() => _showCommands = shouldShow);
    }
  }

  void _submit() {
    final text = _controller.text.trim();
    if (text.isEmpty) return;

    final classId = ref.read(currentClassIdProvider);
    if (classId == null) return;

    ref
        .read(chatMessagesProvider(classId).notifier)
        .addMessage(
          ChatMessage(
            id: 'msg-${DateTime.now().millisecondsSinceEpoch}',
            role: ChatRole.user,
            content: text,
            command: text.startsWith('/') ? text.split(' ').first : null,
            createdAt: DateTime.now(),
          ),
        );

    _controller.clear();
    _focusNode.requestFocus();
  }

  void _insertCommand(String command) {
    _controller.text = '$command ';
    _controller.selection = TextSelection.collapsed(
      offset: _controller.text.length,
    );
    _focusNode.requestFocus();
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final filter = _controller.text.toLowerCase();

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_showCommands)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHigh,
              border: Border(top: BorderSide(color: theme.dividerColor)),
            ),
            child: Wrap(
              spacing: 4,
              runSpacing: 4,
              children: _commands
                  .where((c) => c.startsWith(filter))
                  .map(
                    (cmd) => ActionChip(
                      label: Text(cmd, style: theme.textTheme.labelSmall),
                      onPressed: () => _insertCommand(cmd),
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                    ),
                  )
                  .toList(),
            ),
          ),
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: theme.dividerColor)),
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  decoration: const InputDecoration(
                    hintText: 'Ask anything, /command...',
                    isDense: true,
                  ),
                  onSubmitted: (_) => _submit(),
                  textInputAction: TextInputAction.send,
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.send, size: 20),
                onPressed: _submit,
                tooltip: 'Send',
              ),
            ],
          ),
        ),
      ],
    );
  }
}
