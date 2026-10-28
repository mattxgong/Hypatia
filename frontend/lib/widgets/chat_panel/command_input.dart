import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/chat_provider.dart';
import '../../providers/class_provider.dart';
import 'rebuild_confirm_dialog.dart';

class ChatCommand {
  const ChatCommand(this.name, this.arguments, this.description);

  final String name;
  final String arguments;
  final String description;
}

const chatCommands = [
  ChatCommand('/ask', '<question>', 'Answer from the wiki, with citations'),
  ChatCommand('/summarize', '<topic>', 'Write a new summary page on a topic'),
  ChatCommand('/remove', '<filename>', 'Delete a source and its wiki pages'),
  ChatCommand('/lint', '', 'Check the wiki for broken links and gaps'),
  ChatCommand('/rebuild', '', 'Regenerate the wiki from every source'),
  ChatCommand('/export', '', 'Export the wiki as markdown files'),
  ChatCommand('/flashcards', '[topic]', 'Make a flashcard deck'),
  ChatCommand('/quiz', '[topic]', 'Make a practice quiz'),
  ChatCommand('/help', '', 'List every command'),
];

class CommandInput extends ConsumerStatefulWidget {
  const CommandInput({super.key});

  @override
  ConsumerState<CommandInput> createState() => _CommandInputState();
}

class _CommandInputState extends ConsumerState<CommandInput> {
  final _controller = TextEditingController();
  late final _focusNode = FocusNode(onKeyEvent: _onKey);
  List<ChatCommand> _suggestions = const [];
  int _highlighted = 0;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onTextChanged);
  }

  void _onTextChanged() {
    final text = _controller.text;
    final typingCommand = text.startsWith('/') && !text.contains(RegExp(r'\s'));
    final matches = typingCommand
        ? chatCommands
              .where((c) => c.name.startsWith(text.toLowerCase()))
              .toList()
        : const <ChatCommand>[];
    if (matches.length != _suggestions.length ||
        !matches.every(_suggestions.contains)) {
      setState(() {
        _suggestions = matches;
        _highlighted = 0;
      });
    }
  }

  /// Enter sends (or picks the highlighted command); Shift+Enter adds a line.
  /// Arrow keys and Tab move through and pick command suggestions.
  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final key = event.logicalKey;
    if (_suggestions.isNotEmpty) {
      if (key == LogicalKeyboardKey.arrowDown ||
          key == LogicalKeyboardKey.arrowUp) {
        final step = key == LogicalKeyboardKey.arrowDown ? 1 : -1;
        setState(() {
          _highlighted = (_highlighted + step) % _suggestions.length;
        });
        return KeyEventResult.handled;
      }
      if (key == LogicalKeyboardKey.tab ||
          (key == LogicalKeyboardKey.enter &&
              !HardwareKeyboard.instance.isShiftPressed)) {
        _insertCommand(_suggestions[_highlighted].name);
        return KeyEventResult.handled;
      }
      if (key == LogicalKeyboardKey.escape) {
        setState(() => _suggestions = const []);
        return KeyEventResult.handled;
      }
    }
    if ((key == LogicalKeyboardKey.enter ||
            key == LogicalKeyboardKey.numpadEnter) &&
        !HardwareKeyboard.instance.isShiftPressed) {
      _submit();
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  Future<void> _submit() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;

    final classId = ref.read(currentClassIdProvider);
    if (classId == null || ref.read(chatAwaitingReplyProvider(classId))) {
      return;
    }

    if (text.split(RegExp(r'\s+')).first == '/rebuild' &&
        !await confirmRebuild(context, ref, classId)) {
      return;
    }
    if (!mounted) return;

    final sent = ref
        .read(chatMessagesProvider(classId).notifier)
        .sendMessage(text);
    // Keep the draft when it couldn't be sent so the user can retry.
    if (!sent) return;

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
    final classId = ref.watch(currentClassIdProvider);
    final awaiting =
        classId != null && ref.watch(chatAwaitingReplyProvider(classId));
    final operation = classId == null
        ? null
        : ref.watch(chatActiveOperationProvider(classId));

    ref.listen(chatInputProvider, (_, draft) {
      if (draft.isEmpty) return;
      _controller.text = draft;
      _controller.selection = TextSelection.collapsed(offset: draft.length);
      _focusNode.requestFocus();
      ref.read(chatInputProvider.notifier).state = '';
    });
    ref.listen(chatInputFocusRequestProvider, (_, _) {
      _focusNode.requestFocus();
    });

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_suggestions.isNotEmpty)
          Container(
            // Keyed so the framework does not match this against the input
            // container below by position when the suggestion list appears
            // or disappears. Without keys both children are bare Containers,
            // so the TextField's element would be rebuilt from scratch on
            // every '/' keystroke and lose focus mid-typing.
            key: const ValueKey('command-suggestions'),
            width: double.infinity,
            constraints: const BoxConstraints(maxHeight: 240),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: theme.dividerColor)),
            ),
            // A Material, not a colored box: ListTile paints its highlight on
            // the nearest Material.
            child: Material(
              color: theme.colorScheme.surfaceContainerHigh,
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final (index, command) in _suggestions.indexed)
                      ListTile(
                        dense: true,
                        visualDensity: VisualDensity.compact,
                        selected: index == _highlighted,
                        selectedTileColor: theme.colorScheme.primaryContainer
                            .withValues(alpha: 0.4),
                        title: Text(
                          command.name,
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontFamily: 'monospace',
                          ),
                        ),
                        subtitle: Text(
                          command.arguments.isEmpty
                              ? command.description
                              : '${command.arguments} · ${command.description}',
                          style: theme.textTheme.labelSmall,
                        ),
                        onTap: () => _insertCommand(command.name),
                      ),
                  ],
                ),
              ),
            ),
          ),
        Container(
          key: const ValueKey('command-input'),
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
                  minLines: 1,
                  maxLines: 6,
                  keyboardType: TextInputType.multiline,
                  decoration: const InputDecoration(
                    hintText: 'Ask anything, /command...',
                    helperText: 'Enter to send · Shift+Enter for a new line',
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              if (operation != null)
                IconButton(
                  icon: const Icon(Icons.stop_circle_outlined),
                  onPressed: () =>
                      ref.read(chatMessagesProvider(classId!).notifier).stop(),
                  tooltip: 'Stop',
                )
              else
                IconButton(
                  icon: awaiting
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.send, size: 20),
                  onPressed: awaiting ? null : _submit,
                  tooltip: awaiting ? 'Waiting for the reply' : 'Send',
                ),
            ],
          ),
        ),
      ],
    );
  }
}
