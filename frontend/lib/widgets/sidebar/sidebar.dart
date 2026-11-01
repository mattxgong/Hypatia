import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/theme.dart';
import '../../providers/backend_provider.dart';
import '../../providers/layout_provider.dart';
import '../../providers/search_provider.dart';
import '../../providers/study_provider.dart';
import '../../providers/theme_provider.dart';
import '../../utils/shortcuts.dart';
import '../remote/remote_access_dialog.dart';
import '../study/study_panel.dart';
import 'add_file_button.dart';
import 'class_dropdown.dart';
import 'provider_selector.dart';
import 'search_bar.dart';
import 'task_indicator.dart';
import 'wiki_tree.dart';

class Sidebar extends ConsumerWidget {
  const Sidebar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final searchQuery = ref.watch(searchQueryProvider);
    final mode = ref.watch(sidebarModeProvider);

    return Material(
      color: theme.colorScheme.surfaceContainerLowest,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 4, 12),
            child: Row(
              children: [
                const Expanded(child: ClassDropdown()),
                IconButton(
                  icon: const Icon(Icons.keyboard_double_arrow_left, size: 18),
                  tooltip: 'Hide sidebar ($shortcutModifierLabel+B)',
                  onPressed: () =>
                      ref.read(sidebarCollapsedProvider.notifier).state = true,
                  constraints: HypatiaTokens.iconButtonSize(context, 36),
                ),
              ],
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: SidebarSearchBar(),
          ),
          if (searchQuery.isNotEmpty) ...[
            const SizedBox(height: 4),
            const SearchModeSelector(),
            const SizedBox(height: 4),
            const SearchCategoryFilter(),
          ],
          const SizedBox(height: 8),
          if (searchQuery.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: SegmentedButton<SidebarMode>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(
                    value: SidebarMode.wiki,
                    icon: Icon(Icons.menu_book_outlined, size: 16),
                    label: Text('Wiki'),
                  ),
                  ButtonSegment(
                    value: SidebarMode.study,
                    icon: Icon(Icons.school_outlined, size: 16),
                    label: Text('Study'),
                  ),
                ],
                selected: {mode},
                onSelectionChanged: (s) {
                  ref.read(sidebarModeProvider.notifier).state = s.first;
                  if (s.first == SidebarMode.wiki) {
                    ref.read(studySelectionProvider.notifier).state = null;
                  }
                },
              ),
            ),
          const SizedBox(height: 4),
          Expanded(
            // ListTiles paint their selected color on the nearest Material,
            // which the list's own clip doesn't cover. Without this one, a
            // scrolled-away highlight shows above and below the list.
            child: ClipRect(
              child: Material(
                type: MaterialType.transparency,
                child: searchQuery.isNotEmpty
                    ? const SearchResults()
                    : mode == SidebarMode.study
                    ? const StudyPanel()
                    : const WikiTree(),
              ),
            ),
          ),
          const Divider(height: 1),
          const Padding(padding: EdgeInsets.all(12), child: AddFileButton()),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: ProviderSelector(),
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.only(left: 12, right: 12, bottom: 8),
            child: Row(
              children: [
                IconButton(
                  icon: Icon(
                    theme.brightness == Brightness.dark
                        ? Icons.light_mode
                        : Icons.dark_mode,
                    size: 18,
                  ),
                  onPressed: () =>
                      ref.read(themeModeProvider.notifier).toggle(),
                  tooltip: 'Toggle theme',
                  iconSize: 18,
                  padding: EdgeInsets.zero,
                  constraints: HypatiaTokens.iconButtonSize(context, 32),
                ),
                // Only the desktop app, which runs the backend, offers it.
                if (ref.watch(backendLauncherProvider) != null)
                  IconButton(
                    icon: const Icon(Icons.phonelink_outlined, size: 18),
                    onPressed: () => showRemoteAccessDialog(context),
                    tooltip: 'Remote access',
                    iconSize: 18,
                    padding: EdgeInsets.zero,
                    constraints: HypatiaTokens.iconButtonSize(context, 32),
                  ),
                const Spacer(),
                const TaskIndicator(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
