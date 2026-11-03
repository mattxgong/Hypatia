import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/layout_provider.dart';
import '../../providers/search_provider.dart';
import '../../providers/study_provider.dart';
import '../../widgets/common/activity_status.dart';
import '../../widgets/common/pane_divider.dart';
import 'home_panes.dart';

const _destinations = [
  (HomeDestination.chat, Icons.chat_bubble_outline, Icons.chat_bubble, 'Chat'),
  (HomeDestination.study, Icons.school_outlined, Icons.school, 'Study'),
  (HomeDestination.sources, Icons.folder_outlined, Icons.folder, 'Sources'),
];

/// Touch-sized: there's no resize cursor on a tablet to show it can be dragged.
const _handleWidth = 24.0;

/// Two panes, for tablets in portrait, foldables and phones in landscape. The
/// primary pane holds the wiki (or the open deck or quiz); the secondary pane
/// holds chat, study or sources, picked from the navigation rail.
class MediumLayout extends ConsumerWidget {
  const MediumLayout({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    var pane = ref.watch(secondaryPaneProvider);
    if (pane == HomeDestination.wiki) pane = HomeDestination.chat;
    final selected = _destinations.indexWhere((d) => d.$1 == pane);
    final fraction = ref.watch(secondaryPaneFractionProvider);

    return Scaffold(
      appBar: const HomeAppBar(),
      body: SafeArea(
        top: false,
        child: Row(
          children: [
            NavigationRail(
              selectedIndex: selected,
              labelType: NavigationRailLabelType.all,
              onDestinationSelected: (index) =>
                  showDestination(ref, _destinations[index].$1),
              destinations: [
                for (final (_, icon, selectedIcon, label) in _destinations)
                  NavigationRailDestination(
                    icon: Icon(icon),
                    selectedIcon: Icon(selectedIcon),
                    label: Text(label),
                  ),
              ],
            ),
            const VerticalDivider(width: 1),
            Expanded(
              child: Column(
                children: [
                  const ActivityStatus(showIdleTitle: false),
                  Expanded(
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final width = constraints.maxWidth - _handleWidth;
                        final secondary = width * fraction;
                        void resize(double delta) {
                          final current = ref.read(
                            secondaryPaneFractionProvider,
                          );
                          ref
                              .read(secondaryPaneFractionProvider.notifier)
                              .state = (current + delta / width).clamp(
                            minSecondaryPaneFraction,
                            maxSecondaryPaneFraction,
                          );
                        }

                        return Row(
                          children: [
                            SizedBox(
                              width: width - secondary,
                              child: const _PrimaryPane(),
                            ),
                            PaneDivider(
                              label: 'Resize panes',
                              value: secondary,
                              width: _handleWidth,
                              showGrip: true,
                              reverseKeyboardDirection: true,
                              onDrag: (dx) => resize(-dx),
                              onIncrease: () => resize(16),
                              onDecrease: () => resize(-16),
                              onReset: () =>
                                  ref
                                          .read(
                                            secondaryPaneFractionProvider
                                                .notifier,
                                          )
                                          .state =
                                      defaultSecondaryPaneFraction,
                            ),
                            SizedBox(
                              width: secondary,
                              child: switch (pane) {
                                HomeDestination.study => const StudyListPane(
                                  showOpen: false,
                                ),
                                HomeDestination.sources => const SourcesPane(),
                                HomeDestination.chat || HomeDestination.wiki =>
                                  const ChatPane(canHide: false),
                              },
                            ),
                          ],
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Search results, the open deck or quiz, or the wiki.
class _PrimaryPane extends ConsumerWidget {
  const _PrimaryPane();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(searchOpenProvider) ||
        ref.watch(searchQueryProvider).isNotEmpty) {
      return const SearchPane();
    }
    final selection = ref.watch(studySelectionProvider);
    if (selection != null) {
      return DetailView(
        backLabel: 'Wiki',
        onBack: () => ref.read(studySelectionProvider.notifier).state = null,
        child: StudyPane(selection: selection),
      );
    }
    return const WikiPane();
  }
}
