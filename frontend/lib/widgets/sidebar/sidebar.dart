import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/theme_provider.dart';
import 'add_file_button.dart';
import 'class_dropdown.dart';
import 'search_bar.dart' as sidebar;
import 'wiki_tree.dart';

class Sidebar extends ConsumerWidget {
  const Sidebar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    return Container(
      color: theme.colorScheme.surfaceContainerLowest,
      child: Column(
        children: [
          const Padding(padding: EdgeInsets.all(12), child: ClassDropdown()),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: sidebar.SidebarSearchBar(),
          ),
          const SizedBox(height: 8),
          const Expanded(child: WikiTree()),
          const Divider(height: 1),
          const Padding(padding: EdgeInsets.all(12), child: AddFileButton()),
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
                  constraints: const BoxConstraints(
                    minWidth: 32,
                    minHeight: 32,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
