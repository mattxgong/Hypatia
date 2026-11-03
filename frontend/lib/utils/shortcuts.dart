import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// Cmd on Apple platforms (an iPad with a keyboard too), Ctrl elsewhere.
bool get usesMetaForShortcuts =>
    defaultTargetPlatform == TargetPlatform.macOS ||
    defaultTargetPlatform == TargetPlatform.iOS;

String get shortcutModifierLabel => usesMetaForShortcuts ? 'Cmd' : 'Ctrl';

/// The platform's usual modifier plus [key], e.g. Cmd+K on macOS and iPadOS,
/// Ctrl+K elsewhere.
SingleActivator platformShortcut(LogicalKeyboardKey key) => SingleActivator(
  key,
  control: !usesMetaForShortcuts,
  meta: usesMetaForShortcuts,
);
