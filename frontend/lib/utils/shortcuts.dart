import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// Cmd on macOS, Ctrl elsewhere.
bool get usesMetaForShortcuts => defaultTargetPlatform == TargetPlatform.macOS;

String get shortcutModifierLabel => usesMetaForShortcuts ? 'Cmd' : 'Ctrl';

/// The platform's usual modifier plus [key], e.g. Cmd+K on macOS, Ctrl+K elsewhere.
SingleActivator platformShortcut(LogicalKeyboardKey key) => SingleActivator(
  key,
  control: !usesMetaForShortcuts,
  meta: usesMetaForShortcuts,
);
