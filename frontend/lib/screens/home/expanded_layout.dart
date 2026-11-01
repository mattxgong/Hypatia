import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/theme.dart';
import '../../providers/layout_provider.dart';
import '../../providers/study_provider.dart';
import '../../widgets/common/activity_status.dart';
import '../../widgets/common/pane_divider.dart';
import '../../widgets/sidebar/sidebar.dart';
import '../../widgets/source_viewer/source_viewer.dart';
import '../../widgets/wiki_viewer/wiki_viewer.dart';
import 'home_panes.dart';

const _minimumCenterWidth = 400.0;

/// A collapsed pane's strip, and the space a resize handle takes (a 1px line
/// inside an easy-to-grab strip): mouse-sized on desktop, finger-sized on a
/// tablet, where the handle also shows a grip.
const _collapsedStripWidth = 32.0;
const _dividerWidth = 12.0;
const _touchStripWidth = 48.0;
const _touchDividerWidth = 24.0;

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
  double dividerWidth = _dividerWidth,
  double stripWidth = _collapsedStripWidth,
}) {
  final fixedWidth =
      (sidebarCollapsed ? stripWidth : dividerWidth) +
      (chatCollapsed ? stripWidth : dividerWidth);
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
    final sideSource = ref.watch(sideSourceProvider);
    final sidebarWidth = ref.watch(sidebarWidthProvider);
    final chatWidth = ref.watch(chatPanelWidthProvider);
    final sidebarCollapsed = ref.watch(sidebarCollapsedProvider);
    final chatCollapsed = ref.watch(chatPanelCollapsedProvider);
    final touch = HypatiaTokens.touch(context);
    final dividerWidth = touch ? _touchDividerWidth : _dividerWidth;
    final stripWidth = touch ? _touchStripWidth : _collapsedStripWidth;

    return Scaffold(
      body: LayoutBuilder(
        builder: (context, constraints) {
          final widths = constrainPanelWidths(
            availableWidth: constraints.maxWidth,
            sidebarWidth: sidebarWidth,
            chatWidth: chatWidth,
            sidebarCollapsed: sidebarCollapsed,
            chatCollapsed: chatCollapsed,
            dividerWidth: dividerWidth,
            stripWidth: stripWidth,
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
                  width: dividerWidth,
                  showGrip: touch,
                  onDrag: resizeSidebar,
                  onIncrease: () => resizeSidebar(16),
                  onDecrease: () => resizeSidebar(-16),
                  onReset: () => ref.read(sidebarWidthProvider.notifier).state =
                      defaultSidebarWidth,
                ),
              ] else
                _CollapsedSidebar(width: stripWidth),
              Expanded(
                child: Column(
                  children: [
                    const _TopBar(),
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: studySelection == null
                                ? const WikiPagePane()
                                : StudyPane(selection: studySelection),
                          ),
                          if (sideSource != null) ...[
                            const VerticalDivider(width: 1),
                            Expanded(
                              child: SourcePanel(
                                request: sideSource,
                                onClose: () =>
                                    ref
                                            .read(sideSourceProvider.notifier)
                                            .state =
                                        null,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              if (!chatCollapsed) ...[
                PaneDivider(
                  label: 'Resize chat panel',
                  value: widths.chat,
                  width: dividerWidth,
                  showGrip: touch,
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
                  width: stripWidth,
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
    required this.width,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final double width;
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
              width: width,
              child: Center(child: Icon(icon, size: 18)),
            ),
          ),
        ),
      ),
    );
  }
}

class _CollapsedSidebar extends ConsumerWidget {
  const _CollapsedSidebar({required this.width});

  final double width;

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
        width: width,
        child: Column(
          children: [
            const SizedBox(height: 4),
            for (final (section, icon, label) in _sections)
              IconButton(
                icon: Icon(icon, size: 18),
                tooltip: label,
                onPressed: () => showSidebarSection(ref, section),
                constraints: BoxConstraints(
                  minWidth: width,
                  minHeight: HypatiaTokens.touch(context) ? 48 : 40,
                ),
                padding: EdgeInsets.zero,
              ),
          ],
        ),
      ),
    );
  }
}
