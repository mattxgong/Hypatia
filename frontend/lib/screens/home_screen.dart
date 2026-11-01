import 'dart:async';

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
import '../utils/window_size.dart';
import '../widgets/common/activity_status.dart';
import '../widgets/sidebar/add_file_button.dart';
import '../widgets/sidebar/class_dropdown.dart';
import '../widgets/source_viewer/source_viewer.dart';
import '../widgets/wiki_viewer/wiki_viewer.dart';
import 'home/compact_layout.dart';
import 'home/expanded_layout.dart';
import 'home/home_panes.dart';
import 'home/medium_layout.dart';

export 'home/expanded_layout.dart' show PanelWidths, constrainPanelWidths;

/// A Class: the wiki, chat, study and sources, laid out for the window's size
/// class (compact, medium or expanded). The state behind every layout lives in
/// providers, so the window can change size class at any time (rotation,
/// split-screen, resizing) and the same page, review and draft stay open.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _isDragging = false;
  final _focusNode = FocusNode();
  final _paneKeys = PaneKeys();
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
        prefs.setDouble(
          secondaryPaneFractionKey,
          ref.read(secondaryPaneFractionProvider),
        );
      });
    }

    ref.listen(sidebarWidthProvider, (_, _) => saveWidthsSoon());
    ref.listen(chatPanelWidthProvider, (_, _) => saveWidthsSoon());
    ref.listen(secondaryPaneFractionProvider, (_, _) => saveWidthsSoon());
  }

  @override
  Widget build(BuildContext context) {
    final sizeClass = windowSizeClassOf(context);
    final expanded = sizeClass == WindowSizeClass.expanded;
    _persistLayout();
    ref.listen(chatRevealRequestProvider, (_, _) {
      ref.read(chatPanelCollapsedProvider.notifier).state = false;
      showDestination(ref, HomeDestination.chat);
    });
    ref.listen(sourceViewerRequestProvider, (prev, next) {
      if (next != null) {
        showSourceViewer(context, next);
        ref.read(sourceViewerRequestProvider.notifier).state = null;
      }
    });
    ref.listen(currentWikiPagePathProvider, (_, path) {
      // Opening a wiki page leaves the study view where the two share a
      // pane. On a phone each has its own tab, so a review stays open on the
      // Study tab while the wiki is browsed.
      if (windowSizeClassOf(context) != WindowSizeClass.compact) {
        ref.read(studySelectionProvider.notifier).state = null;
      }
      if (path != null) {
        ref.read(compactDestinationProvider.notifier).state =
            HomeDestination.wiki;
        ref.read(searchOpenProvider.notifier).state = false;
      }
    });
    ref.listen(studySelectionProvider, (_, selection) {
      if (selection != null) {
        ref.read(compactDestinationProvider.notifier).state =
            HomeDestination.study;
      }
    });
    ref.listen(currentClassIdProvider, (_, _) {
      ref.read(studySelectionProvider.notifier).state = null;
      // The open page and the search belong to the previous Class.
      ref.read(currentWikiPagePathProvider.notifier).state = null;
      ref.read(searchQueryProvider.notifier).state = '';
      ref.read(searchOpenProvider.notifier).state = false;
    });

    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        platformShortcut(LogicalKeyboardKey.keyK): () {
          if (!expanded) return openSearch(ref);
          ref.read(sidebarCollapsedProvider.notifier).state = false;
          ref.read(searchBarFocusNodeProvider).requestFocus();
        },
        platformShortcut(LogicalKeyboardKey.keyN): () {
          showCreateClassDialog(context, ref);
        },
        // The side panes only collapse in the three-pane layout.
        platformShortcut(LogicalKeyboardKey.keyB): () {
          if (!expanded) return;
          final collapsed = ref.read(sidebarCollapsedProvider.notifier);
          collapsed.state = !collapsed.state;
        },
        platformShortcut(LogicalKeyboardKey.keyJ): () {
          if (!expanded) return;
          final collapsed = ref.read(chatPanelCollapsedProvider.notifier);
          collapsed.state = !collapsed.state;
        },
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (ref.read(searchQueryProvider).isNotEmpty ||
              ref.read(searchOpenProvider)) {
            closeSearch(ref);
          }
        },
      },
      child: Focus(
        focusNode: _focusNode,
        autofocus: true,
        child: HomePaneKeys(
          keys: _paneKeys,
          child: _BackHandler(
            sizeClass: sizeClass,
            child: SourceFileEvents(
              child: _dropTarget(
                Stack(
                  children: [
                    switch (sizeClass) {
                      WindowSizeClass.compact => const CompactLayout(),
                      WindowSizeClass.medium => const MediumLayout(),
                      WindowSizeClass.expanded => const ExpandedLayout(),
                    },
                    if (_isDragging) const _DropOverlay(),
                  ],
                ),
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

/// Back (the Android back gesture or button) steps out of what's open, one
/// step at a time, before it leaves the Class: search, then the open deck,
/// quiz or page, then (on a phone) back to the Wiki tab.
class _BackHandler extends ConsumerWidget {
  const _BackHandler({required this.sizeClass, required this.child});

  final WindowSizeClass sizeClass;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final searching =
        ref.watch(searchQueryProvider).isNotEmpty ||
        (sizeClass != WindowSizeClass.expanded &&
            ref.watch(searchOpenProvider));
    final selection = ref.watch(studySelectionProvider);
    final page = ref.watch(currentWikiPagePathProvider);
    final tab = ref.watch(compactDestinationProvider);

    void closeStudy() => ref.read(studySelectionProvider.notifier).state = null;
    void closePage() =>
        ref.read(currentWikiPagePathProvider.notifier).state = null;

    final VoidCallback? step = searching
        ? () => closeSearch(ref)
        : switch (sizeClass) {
            WindowSizeClass.compact => switch (tab) {
              HomeDestination.study when selection != null => closeStudy,
              HomeDestination.wiki when page != null => closePage,
              HomeDestination.wiki => null,
              _ => () => showDestination(ref, HomeDestination.wiki),
            },
            WindowSizeClass.medium =>
              selection != null
                  ? closeStudy
                  : page != null
                  ? closePage
                  : null,
            WindowSizeClass.expanded => selection != null ? closeStudy : null,
          };

    return PopScope(
      canPop: step == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) step?.call();
      },
      child: child,
    );
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
