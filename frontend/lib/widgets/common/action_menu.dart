import 'package:flutter/material.dart';

import '../../utils/window_size.dart';

/// One entry in [showActionMenu].
class ActionMenuItem<T> {
  const ActionMenuItem({
    required this.value,
    required this.icon,
    required this.label,
    this.enabled = true,
  });

  final T value;
  final IconData icon;
  final String label;
  final bool enabled;
}

/// Actions for something right-clicked or long-pressed: a menu at [position],
/// or on a phone, a bottom sheet titled [title] that a thumb can reach.
Future<T?> showActionMenu<T>(
  BuildContext context, {
  required String title,
  required Offset position,
  required List<ActionMenuItem<T>> items,
}) {
  if (windowSizeClassOf(context) == WindowSizeClass.compact) {
    return showModalBottomSheet<T>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
              child: Text(
                title,
                style: Theme.of(context).textTheme.titleMedium,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            for (final item in items)
              ListTile(
                leading: Icon(item.icon),
                title: Text(item.label),
                enabled: item.enabled,
                onTap: () => Navigator.of(context).pop(item.value),
              ),
          ],
        ),
      ),
    );
  }

  final overlay = Overlay.of(context).context.findRenderObject()! as RenderBox;
  return showMenu<T>(
    context: context,
    position: RelativeRect.fromRect(
      position & const Size(1, 1),
      Offset.zero & overlay.size,
    ),
    items: [
      for (final item in items)
        PopupMenuItem(
          value: item.value,
          enabled: item.enabled,
          child: ListTile(
            leading: Icon(item.icon),
            title: Text(item.label),
            dense: true,
          ),
        ),
    ],
  );
}
