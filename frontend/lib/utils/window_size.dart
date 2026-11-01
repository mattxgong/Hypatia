import 'package:flutter/widgets.dart';

/// Material 3 window-size classes, by width.
enum WindowSizeClass {
  /// Under 600 dp: phones. One pane at a time, with a bottom navigation bar.
  compact,

  /// 600-840 dp: tablets in portrait, foldables, phones in landscape. Two
  /// panes and a navigation rail.
  medium,

  /// 840 dp and up: tablets in landscape and desktop. Three panes.
  expanded,
}

const compactMaxWidth = 600.0;
const mediumMaxWidth = 840.0;

WindowSizeClass windowSizeClassFor(double width) {
  if (width < compactMaxWidth) return WindowSizeClass.compact;
  if (width < mediumMaxWidth) return WindowSizeClass.medium;
  return WindowSizeClass.expanded;
}

/// From the window, not the screen: Android split-screen and freeform windows,
/// and a resized desktop window, change it while the app runs.
WindowSizeClass windowSizeClassOf(BuildContext context) =>
    windowSizeClassFor(MediaQuery.sizeOf(context).width);
