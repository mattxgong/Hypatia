import 'dart:math' as math;

import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/class_provider.dart';
import '../providers/search_provider.dart';
import '../providers/upload_provider.dart';
import '../widgets/chat_panel/chat_panel.dart';
import '../widgets/sidebar/add_file_button.dart';
import '../widgets/sidebar/class_dropdown.dart';
import '../widgets/sidebar/sidebar.dart';
import '../widgets/source_viewer/source_viewer.dart';
import '../widgets/wiki_viewer/wiki_viewer.dart';

final _sidebarWidthProvider = StateProvider<double>((ref) => 250);
final _chatPanelWidthProvider = StateProvider<double>((ref) => 350);
final _sidebarCollapsedProvider = StateProvider<bool>((ref) => false);
final _chatPanelCollapsedProvider = StateProvider<bool>((ref) => false);

const _minimumCenterWidth = 400.0;
const _minimumSidebarWidth = 180.0;
const _minimumChatWidth = 280.0;
const _collapsedStripWidth = 32.0;
const _dividerWidth = 4.0;

class PanelWidths {
  const PanelWidths({required this.sidebar, required this.chat});

  final double sidebar;
  final double chat;
}

PanelWidths constrainPanelWidths({
  required double availableWidth,
  required double sidebarWidth,
  required double chatWidth,
  required bool sidebarCollapsed,
  required bool chatCollapsed,
}) {
  final fixedWidth =
      (sidebarCollapsed ? _collapsedStripWidth : _dividerWidth) +
      (chatCollapsed ? _collapsedStripWidth : _dividerWidth);
  final sideBudget = math.max(
    0.0,
    availableWidth - fixedWidth - _minimumCenterWidth,
  );

  if (sidebarCollapsed && chatCollapsed) {
    return const PanelWidths(sidebar: 0, chat: 0);
  }
  if (sidebarCollapsed) {
    return PanelWidths(sidebar: 0, chat: math.min(chatWidth, sideBudget));
  }
  if (chatCollapsed) {
    return PanelWidths(sidebar: math.min(sidebarWidth, sideBudget), chat: 0);
  }

  final requestedSidebar = sidebarWidth.clamp(_minimumSidebarWidth, 400.0);
  final requestedChat = chatWidth.clamp(_minimumChatWidth, 500.0);
  const minimumTotal = _minimumSidebarWidth + _minimumChatWidth;
  if (sideBudget < minimumTotal) {
    final scale = sideBudget / minimumTotal;
    return PanelWidths(
      sidebar: _minimumSidebarWidth * scale,
      chat: _minimumChatWidth * scale,
    );
  }

  final requestedExtra =
      (requestedSidebar - _minimumSidebarWidth) +
      (requestedChat - _minimumChatWidth);
  if (requestedSidebar + requestedChat <= sideBudget || requestedExtra == 0) {
    return PanelWidths(sidebar: requestedSidebar, chat: requestedChat);
  }

  final availableExtra = sideBudget - minimumTotal;
  return PanelWidths(
    sidebar:
        _minimumSidebarWidth +
        availableExtra *
            (requestedSidebar - _minimumSidebarWidth) /
            requestedExtra,
    chat:
        _minimumChatWidth +
        availableExtra * (requestedChat - _minimumChatWidth) / requestedExtra,
  );
}

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _isDragging = false;
  final _focusNode = FocusNode();

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(sourceViewerRequestProvider, (prev, next) {
      if (next != null) {
        showSourceViewer(context, next);
        ref.read(sourceViewerRequestProvider.notifier).state = null;
      }
    });
    final sidebarWidth = ref.watch(_sidebarWidthProvider);
    final chatWidth = ref.watch(_chatPanelWidthProvider);
    final sidebarCollapsed = ref.watch(_sidebarCollapsedProvider);
    final chatCollapsed = ref.watch(_chatPanelCollapsedProvider);

    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.keyK, control: true): () {
          if (sidebarCollapsed) {
            ref.read(_sidebarCollapsedProvider.notifier).state = false;
          }
          ref.read(searchBarFocusNodeProvider).requestFocus();
        },
        const SingleActivator(LogicalKeyboardKey.keyN, control: true): () {
          showCreateClassDialog(context, ref);
        },
        const SingleActivator(LogicalKeyboardKey.keyB, control: true): () {
          ref.read(_sidebarCollapsedProvider.notifier).state =
              !sidebarCollapsed;
        },
        const SingleActivator(LogicalKeyboardKey.keyJ, control: true): () {
          ref.read(_chatPanelCollapsedProvider.notifier).state = !chatCollapsed;
        },
        const SingleActivator(LogicalKeyboardKey.escape): () {
          final query = ref.read(searchQueryProvider);
          if (query.isNotEmpty) {
            ref.read(searchQueryProvider.notifier).state = '';
          }
        },
      },
      child: Focus(
        focusNode: _focusNode,
        autofocus: true,
        child: Scaffold(
          body: DropTarget(
            onDragEntered: (_) => setState(() => _isDragging = true),
            onDragExited: (_) => setState(() => _isDragging = false),
            onDragDone: (details) {
              setState(() => _isDragging = false);
              _handleDrop(details);
            },
            child: Stack(
              children: [
                LayoutBuilder(
                  builder: (context, constraints) {
                    final widths = constrainPanelWidths(
                      availableWidth: constraints.maxWidth,
                      sidebarWidth: sidebarWidth,
                      chatWidth: chatWidth,
                      sidebarCollapsed: sidebarCollapsed,
                      chatCollapsed: chatCollapsed,
                    );
                    void resizeSidebar(double delta) {
                      final current = ref.read(_sidebarWidthProvider);
                      ref.read(_sidebarWidthProvider.notifier).state =
                          (current + delta).clamp(180, 400);
                    }

                    void resizeChat(double delta) {
                      final current = ref.read(_chatPanelWidthProvider);
                      ref.read(_chatPanelWidthProvider.notifier).state =
                          (current + delta).clamp(280, 500);
                    }

                    return Row(
                      children: [
                        if (!sidebarCollapsed) ...[
                          SizedBox(
                            width: widths.sidebar,
                            child: const Sidebar(),
                          ),
                          _DraggableDivider(
                            label: 'Resize class sidebar',
                            value: widths.sidebar,
                            onDrag: resizeSidebar,
                            onIncrease: () => resizeSidebar(16),
                            onDecrease: () => resizeSidebar(-16),
                          ),
                        ] else
                          _CollapsedPanelStrip(
                            icon: Icons.menu,
                            label: 'Show class sidebar',
                            onTap: () =>
                                ref
                                        .read(
                                          _sidebarCollapsedProvider.notifier,
                                        )
                                        .state =
                                    false,
                          ),
                        Expanded(
                          child: Column(
                            children: [
                              _TopBar(
                                sidebarCollapsed: sidebarCollapsed,
                                chatCollapsed: chatCollapsed,
                                onToggleSidebar: () =>
                                    ref
                                            .read(
                                              _sidebarCollapsedProvider
                                                  .notifier,
                                            )
                                            .state =
                                        !sidebarCollapsed,
                                onToggleChat: () =>
                                    ref
                                            .read(
                                              _chatPanelCollapsedProvider
                                                  .notifier,
                                            )
                                            .state =
                                        !chatCollapsed,
                              ),
                              const Expanded(child: WikiViewer()),
                            ],
                          ),
                        ),
                        if (!chatCollapsed) ...[
                          _DraggableDivider(
                            label: 'Resize chat panel',
                            value: widths.chat,
                            reverseKeyboardDirection: true,
                            onDrag: (delta) => resizeChat(-delta),
                            onIncrease: () => resizeChat(16),
                            onDecrease: () => resizeChat(-16),
                          ),
                          SizedBox(
                            width: widths.chat,
                            child: const ChatPanel(),
                          ),
                        ] else
                          _CollapsedPanelStrip(
                            icon: Icons.chat_bubble_outline,
                            label: 'Show chat panel',
                            onTap: () =>
                                ref
                                        .read(
                                          _chatPanelCollapsedProvider.notifier,
                                        )
                                        .state =
                                    false,
                          ),
                      ],
                    );
                  },
                ),
                if (_isDragging) const _DropOverlay(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _handleDrop(DropDoneDetails details) {
    final classId = ref.read(currentClassIdProvider);
    if (classId == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Select a class first')));
      return;
    }

    final paths = <String>[];
    final rejected = <String>[];

    for (final file in details.files) {
      final path = file.path;
      final ext = path.split('.').last.toLowerCase();
      if (allowedExtensions.contains(ext)) {
        paths.add(path);
      } else {
        rejected.add(path.split(RegExp(r'[/\\]')).last);
      }
    }

    if (rejected.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Unsupported: ${rejected.take(3).join(", ")}${rejected.length > 3 ? "..." : ""}',
          ),
        ),
      );
    }

    if (paths.isNotEmpty) {
      ref.read(uploadProgressProvider.notifier).uploadFiles(paths);
    }
  }
}

class _DropOverlay extends StatelessWidget {
  const _DropOverlay();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      color: theme.colorScheme.primary.withValues(alpha: 0.1),
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: theme.colorScheme.primary, width: 2),
            boxShadow: [
              BoxShadow(
                color: theme.colorScheme.primary.withValues(alpha: 0.2),
                blurRadius: 20,
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.cloud_upload_outlined,
                size: 48,
                color: theme.colorScheme.primary,
              ),
              const SizedBox(height: 12),
              Text(
                'Drop files to upload',
                style: theme.textTheme.titleMedium?.copyWith(
                  color: theme.colorScheme.primary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.sidebarCollapsed,
    required this.chatCollapsed,
    required this.onToggleSidebar,
    required this.onToggleChat,
  });

  final bool sidebarCollapsed;
  final bool chatCollapsed;
  final VoidCallback onToggleSidebar;
  final VoidCallback onToggleChat;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      height: 40,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: theme.appBarTheme.backgroundColor ?? theme.colorScheme.surface,
        border: Border(bottom: BorderSide(color: theme.dividerColor)),
      ),
      child: Row(
        children: [
          IconButton(
            icon: Icon(
              sidebarCollapsed ? Icons.menu : Icons.menu_open,
              size: 18,
            ),
            onPressed: onToggleSidebar,
            tooltip: sidebarCollapsed
                ? 'Show sidebar (Ctrl+B)'
                : 'Hide sidebar (Ctrl+B)',
            iconSize: 18,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
          ),
          const Spacer(),
          Text('Hypatia', style: theme.textTheme.titleSmall),
          const Spacer(),
          IconButton(
            icon: Icon(
              chatCollapsed ? Icons.chat_bubble_outline : Icons.chat_bubble,
              size: 18,
            ),
            onPressed: onToggleChat,
            tooltip: chatCollapsed
                ? 'Show chat (Ctrl+J)'
                : 'Hide chat (Ctrl+J)',
            iconSize: 18,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
          ),
        ],
      ),
    );
  }
}

class _DraggableDivider extends StatelessWidget {
  const _DraggableDivider({
    required this.label,
    required this.value,
    required this.onDrag,
    required this.onIncrease,
    required this.onDecrease,
    this.reverseKeyboardDirection = false,
  });

  final String label;
  final double value;
  final void Function(double dx) onDrag;
  final VoidCallback onIncrease;
  final VoidCallback onDecrease;
  final bool reverseKeyboardDirection;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      value: '${value.round()} pixels',
      increasedValue: '${(value + 16).round()} pixels',
      decreasedValue: '${math.max(0, value - 16).round()} pixels',
      onIncrease: onIncrease,
      onDecrease: onDecrease,
      child: Focus(
        onKeyEvent: (_, event) {
          if (event is! KeyDownEvent) return KeyEventResult.ignored;
          if (event.logicalKey == LogicalKeyboardKey.arrowRight) {
            reverseKeyboardDirection ? onDecrease() : onIncrease();
            return KeyEventResult.handled;
          }
          if (event.logicalKey == LogicalKeyboardKey.arrowLeft) {
            reverseKeyboardDirection ? onIncrease() : onDecrease();
            return KeyEventResult.handled;
          }
          return KeyEventResult.ignored;
        },
        child: MouseRegion(
          cursor: SystemMouseCursors.resizeColumn,
          child: GestureDetector(
            onHorizontalDragUpdate: (details) => onDrag(details.delta.dx),
            child: Container(
              width: _dividerWidth,
              color: Theme.of(context).dividerColor,
            ),
          ),
        ),
      ),
    );
  }
}

class _CollapsedPanelStrip extends StatelessWidget {
  const _CollapsedPanelStrip({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: Tooltip(
        message: label,
        child: Material(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          child: InkWell(
            onTap: onTap,
            child: SizedBox(
              width: _collapsedStripWidth,
              child: Center(child: Icon(icon, size: 18)),
            ),
          ),
        ),
      ),
    );
  }
}
