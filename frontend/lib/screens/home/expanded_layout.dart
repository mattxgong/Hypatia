import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/layout_provider.dart';
import '../../providers/study_provider.dart';
import '../../widgets/common/activity_status.dart';
import '../../widgets/common/pane_divider.dart';
import '../../widgets/sidebar/sidebar.dart';
import 'home_panes.dart';

const _minimumCenterWidth = 400.0;
const _collapsedStripWidth = 32.0;

/// Space a resize handle takes: a 1px line inside an easy-to-grab strip.
const _dividerWidth = 12.0;

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

  final requestedSidebar = sidebarWidth.clamp(minSidebarWidth, maxSidebarWidth);
  final requestedChat = chatWidth.clamp(minChatWidth, maxChatWidth);
  const minimumTotal = minSidebarWidth + minChatWidth;
  if (sideBudget < minimumTotal) {
    final scale = sideBudget / minimumTotal;
    return PanelWidths(
      sidebar: minSidebarWidth * scale,
      chat: minChatWidth * scale,
    );
  }

  final requestedExtra =
      (requestedSidebar - minSidebarWidth) + (requestedChat - minChatWidth);
  if (requestedSidebar + requestedChat <= sideBudget || requestedExtra == 0) {
    return PanelWidths(sidebar: requestedSidebar, chat: requestedChat);
  }

  final availableExtra = sideBudget - minimumTotal;
  return PanelWidths(
    sidebar:
        minSidebarWidth +
        availableExtra * (requestedSidebar - minSidebarWidth) / requestedExtra,
    chat:
        minChatWidth +
        availableExtra * (requestedChat - minChatWidth) / requestedExtra,
  );
}

/// Three panes, for tablets in landscape and desktop: the sidebar, the wiki
/// page or open deck or quiz, and chat. The side panes resize and collapse.
class ExpandedLayout extends ConsumerWidget {
  const ExpandedLayout({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final studySelection = ref.watch(studySelectionProvider);
    final sidebarWidth = ref.watch(sidebarWidthProvider);
    final chatWidth = ref.watch(chatPanelWidthProvider);
    final sidebarCollapsed = ref.watch(sidebarCollapsedProvider);
    final chatCollapsed = ref.watch(chatPanelCollapsedProvider);

    return Scaffold(
      body: LayoutBuilder(
        builder: (context, constraints) {
          final widths = constrainPanelWidths(
            availableWidth: constraints.maxWidth,
            sidebarWidth: sidebarWidth,
            chatWidth: chatWidth,
            sidebarCollapsed: sidebarCollapsed,
            chatCollapsed: chatCollapsed,
          );
          void resizeSidebar(double delta) {
            final current = ref.read(sidebarWidthProvider);
            ref.read(sidebarWidthProvider.notifier).state = (current + delta)
                .clamp(minSidebarWidth, maxSidebarWidth);
          }

          void resizeChat(double delta) {
            final current = ref.read(chatPanelWidthProvider);
            ref.read(chatPanelWidthProvider.notifier).state = (current + delta)
                .clamp(minChatWidth, maxChatWidth);
          }

          return Row(
            children: [
              if (!sidebarCollapsed) ...[
                SizedBox(width: widths.sidebar, child: const Sidebar()),
                PaneDivider(
                  label: 'Resize class sidebar',
                  value: widths.sidebar,
                  width: _dividerWidth,
                  onDrag: resizeSidebar,
                  onIncrease: () => resizeSidebar(16),
                  onDecrease: () => resizeSidebar(-16),
                  onReset: () => ref.read(sidebarWidthProvider.notifier).state =
                      defaultSidebarWidth,
                ),
              ] else
                const _CollapsedSidebar(),
              Expanded(
                child: Column(
                  children: [
                    const _TopBar(),
                    Expanded(
                      child: studySelection == null
                          ? const WikiPagePane()
                          : StudyPane(selection: studySelection),
                    ),
                  ],
                ),
              ),
              if (!chatCollapsed) ...[
                PaneDivider(
                  label: 'Resize chat panel',
                  value: widths.chat,
                  width: _dividerWidth,
                  reverseKeyboardDirection: true,
                  onDrag: (delta) => resizeChat(-delta),
                  onIncrease: () => resizeChat(16),
                  onDecrease: () => resizeChat(-16),
                  onReset: () =>
                      ref.read(chatPanelWidthProvider.notifier).state =
                          defaultChatWidth,
                ),
                SizedBox(width: widths.chat, child: const ChatPane()),
              ] else
                _CollapsedPanelStrip(
                  icon: Icons.chat_bubble_outline,
                  label: 'Show chat panel',
                  onTap: () =>
                      ref.read(chatPanelCollapsedProvider.notifier).state =
                          false,
                ),
            ],
          );
        },
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar();

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
      child: const Center(child: ActivityStatus()),
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

class _CollapsedSidebar extends ConsumerWidget {
  const _CollapsedSidebar();

  static const _sections = [
    (SidebarSection.wiki, Icons.menu_book_outlined, 'Wiki'),
    (SidebarSection.sources, Icons.folder_outlined, 'Source files'),
    (SidebarSection.study, Icons.school_outlined, 'Study'),
    (SidebarSection.search, Icons.search, 'Search'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: SizedBox(
        width: _collapsedStripWidth,
        child: Column(
          children: [
            const SizedBox(height: 4),
            for (final (section, icon, label) in _sections)
              IconButton(
                icon: Icon(icon, size: 18),
                tooltip: label,
                onPressed: () => showSidebarSection(ref, section),
                constraints: const BoxConstraints(
                  minWidth: _collapsedStripWidth,
                  minHeight: 40,
                ),
                padding: EdgeInsets.zero,
              ),
          ],
        ),
      ),
    );
  }
}
