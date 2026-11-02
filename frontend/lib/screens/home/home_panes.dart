import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/backend_provider.dart';
import '../../providers/class_provider.dart';
import '../../providers/connection_provider.dart';
import '../../providers/layout_provider.dart';
import '../../providers/search_provider.dart';
import '../../providers/study_provider.dart';
import '../../providers/theme_provider.dart';
import '../../providers/wiki_provider.dart';
import '../../utils/shortcuts.dart';
import '../../widgets/chat_panel/chat_panel.dart';
import '../../widgets/common/hypatia_about_button.dart';
import '../../widgets/remote/connection_gate.dart';
import '../../widgets/remote/remote_access_dialog.dart';
import '../../widgets/sidebar/add_file_button.dart';
import '../../widgets/sidebar/class_dropdown.dart';
import '../../widgets/sidebar/provider_selector.dart';
import '../../widgets/sidebar/search_bar.dart';
import '../../widgets/sidebar/task_indicator.dart';
import '../../widgets/sidebar/wiki_tree.dart';
import '../../widgets/study/flashcard_review.dart';
import '../../widgets/study/quiz_view.dart';
import '../../widgets/study/study_panel.dart';
import '../../widgets/wiki_viewer/wiki_viewer.dart';

/// Keys for the panes that hold state worth keeping (a review session, the
/// open page's scroll position, the chat's), so that when the window changes
/// size class and the layout is rebuilt, each moves to its new place instead
/// of starting over. A GlobalKey keeps its State when its widget moves within
/// one frame. Made once per home screen, which outlives its layouts.
class PaneKeys {
  final chat = GlobalKey(debugLabel: 'chat');
  final wikiPage = GlobalKey(debugLabel: 'wikiPage');
  final study = GlobalKey(debugLabel: 'study');
}

class HomePaneKeys extends InheritedWidget {
  const HomePaneKeys({super.key, required this.keys, required super.child});

  final PaneKeys keys;

  static PaneKeys of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<HomePaneKeys>()!.keys;

  @override
  bool updateShouldNotify(HomePaneKeys oldWidget) => keys != oldWidget.keys;
}

class ChatPane extends StatelessWidget {
  const ChatPane({super.key, this.canHide = true});

  final bool canHide;

  @override
  Widget build(BuildContext context) => KeyedSubtree(
    key: HomePaneKeys.of(context).chat,
    child: ChatPanel(canHide: canHide),
  );
}

class WikiPagePane extends StatelessWidget {
  const WikiPagePane({super.key});

  @override
  Widget build(BuildContext context) => KeyedSubtree(
    key: HomePaneKeys.of(context).wikiPage,
    child: const WikiViewer(),
  );
}

/// The open deck's review or the open quiz.
class StudyPane extends StatelessWidget {
  const StudyPane({super.key, required this.selection});

  final StudySelection selection;

  @override
  Widget build(BuildContext context) => KeyedSubtree(
    key: HomePaneKeys.of(context).study,
    child: switch (selection) {
      StudySelection(kind: StudyKind.deck, :final id) => FlashcardReview(
        key: ValueKey('deck-$id'),
        deckId: id,
      ),
      StudySelection(kind: StudyKind.quiz, :final id) => QuizView(
        key: ValueKey('quiz-$id'),
        quizId: id,
      ),
    },
  );
}

/// A page opened from a list, with a way back to the list.
class DetailView extends StatelessWidget {
  const DetailView({
    super.key,
    required this.backLabel,
    required this.onBack,
    required this.child,
  });

  /// Names the list Back returns to ("Wiki", "Study").
  final String backLabel;
  final VoidCallback onBack;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: Padding(
            padding: const EdgeInsets.only(left: 4, top: 4),
            child: TextButton.icon(
              onPressed: onBack,
              icon: const Icon(Icons.arrow_back, size: 18),
              label: Text(backLabel),
            ),
          ),
        ),
        Expanded(child: child),
      ],
    );
  }
}

/// The wiki: its pages, or the open page with a way back to them.
class WikiPane extends ConsumerWidget {
  const WikiPane({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(currentWikiPagePathProvider) == null) {
      return const _PaneMaterial(
        child: WikiTree(content: WikiTreeContent.pages),
      );
    }
    return DetailView(
      backLabel: 'Wiki',
      onBack: () => ref.read(currentWikiPagePathProvider.notifier).state = null,
      child: const WikiPagePane(),
    );
  }
}

/// Decks and quizzes, or the open one with a way back to them.
class StudyListPane extends ConsumerWidget {
  const StudyListPane({super.key, this.showOpen = true});

  /// Whether the open deck or quiz replaces the list. The medium layout shows
  /// it in the primary pane instead, beside the list.
  final bool showOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selection = ref.watch(studySelectionProvider);
    if (!showOpen || selection == null) {
      return const _PaneMaterial(child: StudyPanel());
    }
    return DetailView(
      backLabel: 'Study',
      onBack: () => ref.read(studySelectionProvider.notifier).state = null,
      child: StudyPane(selection: selection),
    );
  }
}

/// The Class's source files, and the button to add more.
class SourcesPane extends StatelessWidget {
  const SourcesPane({super.key});

  @override
  Widget build(BuildContext context) {
    return const _PaneMaterial(
      child: Column(
        children: [
          Expanded(child: WikiTree(content: WikiTreeContent.sources)),
          Divider(height: 1),
          Padding(padding: EdgeInsets.all(12), child: AddFileButton()),
        ],
      ),
    );
  }
}

/// Results for the app bar's search box.
class SearchPane extends ConsumerWidget {
  const SearchPane({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(searchQueryProvider).isEmpty) {
      return _PaneMaterial(
        child: Center(
          child: Text(
            "Search this class's wiki.",
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
      );
    }
    return const _PaneMaterial(
      child: Column(
        children: [
          SizedBox(height: 4),
          SearchModeSelector(),
          SizedBox(height: 4),
          SearchCategoryFilter(),
          Expanded(child: SearchResults()),
        ],
      ),
    );
  }
}

/// List tiles paint their selected color on the nearest Material, which a
/// list's clip doesn't cover, so each list gets its own.
class _PaneMaterial extends StatelessWidget {
  const _PaneMaterial({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => ClipRect(
    child: Material(
      color: Theme.of(context).colorScheme.surfaceContainerLowest,
      child: child,
    ),
  );
}

void openSearch(WidgetRef ref) {
  ref.read(searchOpenProvider.notifier).state = true;
  // The box is built with the app bar, on the next frame.
  WidgetsBinding.instance.addPostFrameCallback(
    (_) => ref.read(searchBarFocusNodeProvider).requestFocus(),
  );
}

void closeSearch(WidgetRef ref) {
  ref.read(searchQueryProvider.notifier).state = '';
  ref.read(searchOpenProvider.notifier).state = false;
}

/// The compact and medium layouts' app bar: the Class, search, running tasks
/// and a menu with what the expanded layout's sidebar has around its edges.
class HomeAppBar extends ConsumerWidget implements PreferredSizeWidget {
  const HomeAppBar({super.key});

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(searchOpenProvider)) {
      return AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Close search',
          onPressed: () => closeSearch(ref),
        ),
        titleSpacing: 0,
        title: const Padding(
          padding: EdgeInsets.only(right: 12),
          child: SidebarSearchBar(),
        ),
      );
    }
    return AppBar(
      titleSpacing: 12,
      title: const ClassDropdown(showActions: false),
      actions: [
        IconButton(
          icon: const Icon(Icons.search),
          tooltip: 'Search wiki ($shortcutModifierLabel+K)',
          onPressed: () => openSearch(ref),
        ),
        const TaskIndicator(),
        const _MoreMenu(),
      ],
    );
  }
}

enum _MoreAction {
  newClass,
  importClass,
  classSettings,
  aiProvider,
  theme,
  remoteAccess,
  pairedComputer,
  about,
}

class _MoreMenu extends ConsumerWidget {
  const _MoreMenu();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    final dark = Theme.of(context).brightness == Brightness.dark;
    // Only the desktop app, which runs the backend, offers it.
    final canShareBackend = ref.watch(backendLauncherProvider) != null;
    final remoteClient = ref.watch(remoteClientProvider);

    PopupMenuItem<_MoreAction> item(
      _MoreAction value,
      IconData icon,
      String label,
    ) => PopupMenuItem(
      value: value,
      child: ListTile(
        leading: Icon(icon),
        title: Text(label),
        contentPadding: EdgeInsets.zero,
      ),
    );

    return PopupMenuButton<_MoreAction>(
      tooltip: 'More',
      icon: const Icon(Icons.more_vert),
      onSelected: (action) {
        switch (action) {
          case _MoreAction.newClass:
            showCreateClassDialog(context, ref);
          case _MoreAction.importClass:
            importClassFromBackup(context, ref);
          case _MoreAction.classSettings:
            if (classId != null) openClassSettings(context, classId);
          case _MoreAction.aiProvider:
            _showProviderDialog(context);
          case _MoreAction.theme:
            ref.read(themeModeProvider.notifier).toggle();
          case _MoreAction.remoteAccess:
            showRemoteAccessDialog(context);
          case _MoreAction.pairedComputer:
            showPairedComputerDialog(context);
          case _MoreAction.about:
            showHypatiaAboutDialog(context);
        }
      },
      itemBuilder: (_) => [
        item(_MoreAction.newClass, Icons.add, 'New class…'),
        item(
          _MoreAction.importClass,
          Icons.file_upload_outlined,
          'Import from backup…',
        ),
        if (classId != null)
          item(
            _MoreAction.classSettings,
            Icons.settings_outlined,
            'Class settings',
          ),
        const PopupMenuDivider(),
        item(_MoreAction.aiProvider, Icons.smart_toy_outlined, 'AI provider…'),
        item(
          _MoreAction.theme,
          dark ? Icons.light_mode : Icons.dark_mode,
          dark ? 'Light theme' : 'Dark theme',
        ),
        if (canShareBackend)
          item(
            _MoreAction.remoteAccess,
            Icons.phonelink_outlined,
            'Remote access…',
          ),
        if (remoteClient)
          item(
            _MoreAction.pairedComputer,
            Icons.computer_outlined,
            'Your computer…',
          ),
        item(_MoreAction.about, Icons.info_outline, 'About Hypatia'),
      ],
    );
  }

  void _showProviderDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('AI provider'),
        content: const SizedBox(width: 400, child: ProviderSelector()),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}
