import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/class_provider.dart';
import '../providers/upload_provider.dart';
import '../widgets/chat_panel/chat_panel.dart';
import '../widgets/sidebar/add_file_button.dart';
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
  bool _isDragging = false;

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
      body: DropTarget(
        onDragEntered: (_) => setState(() => _isDragging = true),
        onDragExited: (_) => setState(() => _isDragging = false),
        onDragDone: (details) {
          setState(() => _isDragging = false);
          _handleDrop(details);
        },
        child: Stack(
          children: [
            Row(
              children: [
                if (!sidebarCollapsed) ...[
                  SizedBox(width: sidebarWidth, child: const Sidebar()),
                  _DraggableDivider(
                    onDrag: (dx) {
                      final current = ref.read(_sidebarWidthProvider);
                      ref.read(_sidebarWidthProvider.notifier).state =
                          (current + dx).clamp(180, 400);
                    },
                  ),
                ] else
                  _CollapsedPanelStrip(
                    icon: Icons.menu,
                    onTap: () =>
                        ref.read(_sidebarCollapsedProvider.notifier).state =
                            false,
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
                            ref
                                    .read(_chatPanelCollapsedProvider.notifier)
                                    .state =
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
                        ref.read(_chatPanelCollapsedProvider.notifier).state =
                            false,
                  ),
              ],
            ),
            if (_isDragging) const _DropOverlay(),
          ],
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
