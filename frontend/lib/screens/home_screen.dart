import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../widgets/chat_panel/chat_panel.dart';
import '../widgets/sidebar/sidebar.dart';
import '../widgets/source_viewer/source_viewer.dart';
import '../widgets/wiki_viewer/wiki_viewer.dart';

final _sidebarWidthProvider = StateProvider<double>((ref) => 250);
final _chatPanelWidthProvider = StateProvider<double>((ref) => 350);
final _sidebarCollapsedProvider = StateProvider<bool>((ref) => false);
final _chatPanelCollapsedProvider = StateProvider<bool>((ref) => false);

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
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

    return Scaffold(
      body: Row(
        children: [
          if (!sidebarCollapsed) ...[
            SizedBox(width: sidebarWidth, child: const Sidebar()),
            _DraggableDivider(
              onDrag: (dx) {
                final current = ref.read(_sidebarWidthProvider);
                ref.read(_sidebarWidthProvider.notifier).state = (current + dx)
                    .clamp(180, 400);
              },
            ),
          ] else
            _CollapsedPanelStrip(
              icon: Icons.menu,
              onTap: () =>
                  ref.read(_sidebarCollapsedProvider.notifier).state = false,
            ),
          Expanded(
            child: Column(
              children: [
                _TopBar(
                  sidebarCollapsed: sidebarCollapsed,
                  chatCollapsed: chatCollapsed,
                  onToggleSidebar: () =>
                      ref.read(_sidebarCollapsedProvider.notifier).state =
                          !sidebarCollapsed,
                  onToggleChat: () =>
                      ref.read(_chatPanelCollapsedProvider.notifier).state =
                          !chatCollapsed,
                ),
                const Expanded(child: WikiViewer()),
              ],
            ),
          ),
          if (!chatCollapsed) ...[
            _DraggableDivider(
              onDrag: (dx) {
                final current = ref.read(_chatPanelWidthProvider);
                ref.read(_chatPanelWidthProvider.notifier).state =
                    (current - dx).clamp(280, 500);
              },
            ),
            SizedBox(width: chatWidth, child: const ChatPanel()),
          ] else
            _CollapsedPanelStrip(
              icon: Icons.chat_bubble_outline,
              onTap: () =>
                  ref.read(_chatPanelCollapsedProvider.notifier).state = false,
            ),
        ],
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
            tooltip: sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar',
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
            tooltip: chatCollapsed ? 'Show chat' : 'Hide chat',
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
  const _DraggableDivider({required this.onDrag});

  final void Function(double dx) onDrag;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.resizeColumn,
      child: GestureDetector(
        onHorizontalDragUpdate: (details) => onDrag(details.delta.dx),
        child: Container(width: 4, color: Theme.of(context).dividerColor),
      ),
    );
  }
}

class _CollapsedPanelStrip extends StatelessWidget {
  const _CollapsedPanelStrip({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 32,
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Center(child: Icon(icon, size: 18)),
      ),
    );
  }
}
