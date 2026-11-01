import 'dart:async';
import 'dart:math' as math;

import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/theme.dart';
import '../providers/chat_provider.dart';
import '../providers/class_provider.dart';
import '../providers/layout_provider.dart';
import '../providers/search_provider.dart';
import '../providers/study_provider.dart';
import '../providers/theme_provider.dart';
import '../providers/upload_provider.dart';
import '../providers/wiki_provider.dart';
import '../utils/platform.dart';
import '../utils/shortcuts.dart';
import '../widgets/chat_panel/chat_panel.dart';
import '../widgets/common/activity_status.dart';
import '../widgets/sidebar/add_file_button.dart';
import '../widgets/sidebar/class_dropdown.dart';
import '../widgets/sidebar/sidebar.dart';
import '../widgets/source_viewer/source_viewer.dart';
import '../widgets/study/flashcard_review.dart';
import '../widgets/study/quiz_view.dart';
import '../widgets/wiki_viewer/wiki_viewer.dart';

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

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _isDragging = false;
  final _focusNode = FocusNode();
  Timer? _saveWidths;

  @override
  void dispose() {
    _saveWidths?.cancel();
    _focusNode.dispose();
    super.dispose();
  }

  void _persistLayout() {
    final prefs = ref.read(sharedPreferencesProvider);
    ref.listen(sidebarCollapsedProvider, (_, collapsed) {
      prefs.setBool(sidebarCollapsedKey, collapsed);
    });
    ref.listen(chatPanelCollapsedProvider, (_, collapsed) {
      prefs.setBool(chatCollapsedKey, collapsed);
    });
    // Widths change on every pointer move of a drag; save once it settles.
    void saveWidthsSoon() {
      _saveWidths?.cancel();
      _saveWidths = Timer(const Duration(milliseconds: 400), () {
        prefs.setDouble(sidebarWidthKey, ref.read(sidebarWidthProvider));
        prefs.setDouble(chatWidthKey, ref.read(chatPanelWidthProvider));
      });
    }

    ref.listen(sidebarWidthProvider, (_, _) => saveWidthsSoon());
    ref.listen(chatPanelWidthProvider, (_, _) => saveWidthsSoon());
  }

  @override
  Widget build(BuildContext context) {
    _persistLayout();
    ref.listen(chatRevealRequestProvider, (_, _) {
      ref.read(chatPanelCollapsedProvider.notifier).state = false;
    });
    ref.listen(sourceViewerRequestProvider, (prev, next) {
      if (next != null) {
        showSourceViewer(context, next);
        ref.read(sourceViewerRequestProvider.notifier).state = null;
      }
    });
    // Opening a wiki page or switching class leaves the study view.
    ref.listen(currentWikiPagePathProvider, (_, _) {
      ref.read(studySelectionProvider.notifier).state = null;
    });
    ref.listen(currentClassIdProvider, (_, _) {
      ref.read(studySelectionProvider.notifier).state = null;
      // The open page and the search belong to the previous Class.
      ref.read(currentWikiPagePathProvider.notifier).state = null;
      ref.read(searchQueryProvider.notifier).state = '';
    });
    final studySelection = ref.watch(studySelectionProvider);
    final sidebarWidth = ref.watch(sidebarWidthProvider);
    final chatWidth = ref.watch(chatPanelWidthProvider);
    final sidebarCollapsed = ref.watch(sidebarCollapsedProvider);
    final chatCollapsed = ref.watch(chatPanelCollapsedProvider);

    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        platformShortcut(LogicalKeyboardKey.keyK): () {
          if (sidebarCollapsed) {
            ref.read(sidebarCollapsedProvider.notifier).state = false;
          }
          ref.read(searchBarFocusNodeProvider).requestFocus();
        },
        platformShortcut(LogicalKeyboardKey.keyN): () {
          showCreateClassDialog(context, ref);
        },
        platformShortcut(LogicalKeyboardKey.keyB): () {
          ref.read(sidebarCollapsedProvider.notifier).state = !sidebarCollapsed;
        },
        platformShortcut(LogicalKeyboardKey.keyJ): () {
          ref.read(chatPanelCollapsedProvider.notifier).state = !chatCollapsed;
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
          body: SourceFileEvents(
            child: _dropTarget(
              Stack(
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
                        final current = ref.read(sidebarWidthProvider);
                        ref
                            .read(sidebarWidthProvider.notifier)
                            .state = (current + delta).clamp(
                          minSidebarWidth,
                          maxSidebarWidth,
                        );
                      }

                      void resizeChat(double delta) {
                        final current = ref.read(chatPanelWidthProvider);
                        ref.read(chatPanelWidthProvider.notifier).state =
                            (current + delta).clamp(minChatWidth, maxChatWidth);
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
                              onReset: () =>
                                  ref
                                          .read(sidebarWidthProvider.notifier)
                                          .state =
                                      defaultSidebarWidth,
                            ),
                          ] else
                            const _CollapsedSidebar(),
                          Expanded(
                            child: Column(
                              children: [
                                const _TopBar(),
                                Expanded(
                                  child: switch (studySelection) {
                                    StudySelection(
                                      kind: StudyKind.deck,
                                      :final id,
                                    ) =>
                                      FlashcardReview(
                                        key: ValueKey('deck-$id'),
                                        deckId: id,
                                      ),
                                    StudySelection(
                                      kind: StudyKind.quiz,
                                      :final id,
                                    ) =>
                                      QuizView(
                                        key: ValueKey('quiz-$id'),
                                        quizId: id,
                                      ),
                                    null => const WikiViewer(),
                                  },
                                ),
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
                              onReset: () =>
                                  ref
                                          .read(chatPanelWidthProvider.notifier)
                                          .state =
                                      defaultChatWidth,
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
                                            chatPanelCollapsedProvider.notifier,
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
      ),
    );
  }

  /// Accepts files dragged in from the file manager. Desktop only: phones and
  /// tablets add files with the Add File button.
  Widget _dropTarget(Widget child) {
    if (!isDesktop) return child;
    return DropTarget(
      onDragEntered: (_) => setState(() => _isDragging = true),
      onDragExited: (_) => setState(() => _isDragging = false),
      onDragDone: (details) {
        setState(() => _isDragging = false);
        _handleDrop(details);
      },
      child: child,
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
      color: HypatiaTokens.of(context).accentTint,
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: HypatiaTokens.cornersLarge,
            border: Border.all(color: theme.colorScheme.primary, width: 2),
            boxShadow: HypatiaTokens.of(context).shadowHigh,
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

class _DraggableDivider extends StatelessWidget {
  const _DraggableDivider({
    required this.label,
    required this.value,
    required this.onDrag,
    required this.onIncrease,
    required this.onDecrease,
    required this.onReset,
    this.reverseKeyboardDirection = false,
  });

  final String label;
  final double value;
  final void Function(double dx) onDrag;
  final VoidCallback onIncrease;
  final VoidCallback onDecrease;

  /// Back to the pane's default width (double-click).
  final VoidCallback onReset;
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
            onDoubleTap: onReset,
            child: Container(
              width: _dividerWidth,
              color: Colors.transparent,
              alignment: Alignment.center,
              child: Container(width: 1, color: Theme.of(context).dividerColor),
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
