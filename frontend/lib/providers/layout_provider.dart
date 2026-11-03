import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'search_provider.dart';
import 'study_provider.dart';
import 'theme_provider.dart';

// Panel layout is remembered across launches, like the theme.
const sidebarWidthKey = 'hypatia_layout_sidebar_width';
const chatWidthKey = 'hypatia_layout_chat_width';
const sidebarCollapsedKey = 'hypatia_layout_sidebar_collapsed';
const chatCollapsedKey = 'hypatia_layout_chat_collapsed';

const defaultSidebarWidth = 250.0;
const defaultChatWidth = 350.0;
const minSidebarWidth = 180.0;
const maxSidebarWidth = 400.0;
const minChatWidth = 280.0;
const maxChatWidth = 500.0;

/// The width the user chose, clamped on load in case the saved value is from
/// an older version or was edited by hand. The window can still be too narrow
/// for it; `constrainPanelWidths` fits it at layout time.
final sidebarWidthProvider = StateProvider<double>(
  (ref) =>
      (ref.read(sharedPreferencesProvider).getDouble(sidebarWidthKey) ??
              defaultSidebarWidth)
          .clamp(minSidebarWidth, maxSidebarWidth),
);
final chatPanelWidthProvider = StateProvider<double>(
  (ref) =>
      (ref.read(sharedPreferencesProvider).getDouble(chatWidthKey) ??
              defaultChatWidth)
          .clamp(minChatWidth, maxChatWidth),
);
final sidebarCollapsedProvider = StateProvider<bool>(
  (ref) =>
      ref.read(sharedPreferencesProvider).getBool(sidebarCollapsedKey) ?? false,
);
final chatPanelCollapsedProvider = StateProvider<bool>(
  (ref) =>
      ref.read(sharedPreferencesProvider).getBool(chatCollapsedKey) ?? false,
);

/// What the collapsed sidebar's icons open.
enum SidebarSection { wiki, sources, study, search }

/// Set to bring the wiki tree's Source Files section into view. A flag, not
/// an event: the tree may only be built after the sidebar expands. The tree
/// clears it once it has scrolled.
final revealSourcesProvider = StateProvider<bool>((ref) => false);

/// Expands the sidebar on [section].
void showSidebarSection(WidgetRef ref, SidebarSection section) {
  ref.read(sidebarCollapsedProvider.notifier).state = false;
  if (section == SidebarSection.study) {
    ref.read(sidebarModeProvider.notifier).state = SidebarMode.study;
    return;
  }
  ref.read(sidebarModeProvider.notifier).state = SidebarMode.wiki;
  switch (section) {
    case SidebarSection.sources:
      ref.read(revealSourcesProvider.notifier).state = true;
    case SidebarSection.search:
      // The search bar is built on the next frame, with the sidebar.
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => ref.read(searchBarFocusNodeProvider).requestFocus(),
      );
    case SidebarSection.wiki:
    case SidebarSection.study:
      break;
  }
}

/// Where the compact layout's bottom navigation bar is, and which pane the
/// medium layout's rail shows beside the wiki (chat, study or sources; wiki
/// shows chat there).
enum HomeDestination { wiki, chat, study, sources }

final compactDestinationProvider = StateProvider<HomeDestination>(
  (ref) => HomeDestination.wiki,
);
final secondaryPaneProvider = StateProvider<HomeDestination>(
  (ref) => HomeDestination.chat,
);

/// The compact and medium layouts' app bar search, open or not. The expanded
/// layout's search box is always in the sidebar.
final searchOpenProvider = StateProvider<bool>((ref) => false);

const secondaryPaneFractionKey = 'hypatia_layout_secondary_fraction';
const defaultSecondaryPaneFraction = 0.45;
const minSecondaryPaneFraction = 0.3;
const maxSecondaryPaneFraction = 0.7;

/// The medium layout's split: the share of the width the secondary pane takes.
final secondaryPaneFractionProvider = StateProvider<double>(
  (ref) =>
      (ref
                  .read(sharedPreferencesProvider)
                  .getDouble(secondaryPaneFractionKey) ??
              defaultSecondaryPaneFraction)
          .clamp(minSecondaryPaneFraction, maxSecondaryPaneFraction),
);

/// Switches the compact layout's tab, and the medium layout's secondary pane
/// when [destination] is one it shows. Study and wiki also pick the expanded
/// sidebar's mode, so widening the window keeps the same list in view.
void showDestination(WidgetRef ref, HomeDestination destination) {
  ref.read(compactDestinationProvider.notifier).state = destination;
  if (destination != HomeDestination.wiki) {
    ref.read(secondaryPaneProvider.notifier).state = destination;
  }
  switch (destination) {
    case HomeDestination.wiki:
      ref.read(sidebarModeProvider.notifier).state = SidebarMode.wiki;
    case HomeDestination.study:
      ref.read(sidebarModeProvider.notifier).state = SidebarMode.study;
    case HomeDestination.chat:
    case HomeDestination.sources:
      break;
  }
}
