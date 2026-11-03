import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/layout_provider.dart';
import '../../providers/search_provider.dart';
import '../../widgets/common/activity_status.dart';
import 'home_panes.dart';

const _destinations = [
  (HomeDestination.wiki, Icons.menu_book_outlined, Icons.menu_book, 'Wiki'),
  (HomeDestination.chat, Icons.chat_bubble_outline, Icons.chat_bubble, 'Chat'),
  (HomeDestination.study, Icons.school_outlined, Icons.school, 'Study'),
  (HomeDestination.sources, Icons.folder_outlined, Icons.folder, 'Sources'),
];

/// One pane at a time, for phones: Wiki, Chat, Study and Sources tabs in a
/// bottom navigation bar, with the Class and search in the app bar. A page,
/// deck or quiz opened from a list replaces the list, and Back returns to it.
class CompactLayout extends ConsumerWidget {
  const CompactLayout({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final destination = ref.watch(compactDestinationProvider);
    final searching =
        ref.watch(searchOpenProvider) ||
        ref.watch(searchQueryProvider).isNotEmpty;

    return Scaffold(
      appBar: const HomeAppBar(),
      body: Column(
        children: [
          const ActivityStatus(showIdleTitle: false),
          Expanded(
            // Every tab stays built, so switching tabs keeps a review
            // session, the chat's scroll position and the open page.
            child: Stack(
              children: [
                IndexedStack(
                  index: destination.index,
                  sizing: StackFit.expand,
                  children: const [
                    WikiPane(),
                    ChatPane(canHide: false),
                    StudyListPane(),
                    SourcesPane(),
                  ],
                ),
                if (searching) const Positioned.fill(child: SearchPane()),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: destination.index,
        onDestinationSelected: (index) {
          if (searching) closeSearch(ref);
          showDestination(ref, HomeDestination.values[index]);
        },
        destinations: [
          for (final (_, icon, selectedIcon, label) in _destinations)
            NavigationDestination(
              icon: Icon(icon),
              selectedIcon: Icon(selectedIcon),
              label: label,
            ),
        ],
      ),
    );
  }
}
