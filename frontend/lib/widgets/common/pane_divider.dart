import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../config/theme.dart';

/// A vertical resize handle between two panes: drag it, double-click (or
/// double-tap) it to reset, or focus it and use the arrow keys.
class PaneDivider extends StatelessWidget {
  const PaneDivider({
    super.key,
    required this.label,
    required this.value,
    required this.onDrag,
    required this.onIncrease,
    required this.onDecrease,
    required this.onReset,
    this.width = 12,
    this.showGrip = false,
    this.reverseKeyboardDirection = false,
  });

  final String label;

  /// The pane's current width, read out by screen readers.
  final double value;
  final void Function(double dx) onDrag;
  final VoidCallback onIncrease;
  final VoidCallback onDecrease;

  /// Back to the pane's default width.
  final VoidCallback onReset;

  /// The strip that takes the drag, with a 1px line in the middle.
  final double width;

  /// A visible handle on the line, for touch screens where there's no resize
  /// cursor to show the divider can be dragged.
  final bool showGrip;
  final bool reverseKeyboardDirection;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Semantics(
      label: label,
      value: '${value.round()} pixels',
      increasedValue: '${(value + 16).round()} pixels',
      decreasedValue: '${math.max(0, value - 16).round()} pixels',
      onIncrease: onIncrease,
      onDecrease: onDecrease,
      child: Focus(
        onKeyEvent: (_, event) {
          if (event is! KeyDownEvent) return KeyEventResult.ignored;
          if (event.logicalKey == LogicalKeyboardKey.arrowRight) {
            reverseKeyboardDirection ? onDecrease() : onIncrease();
            return KeyEventResult.handled;
          }
          if (event.logicalKey == LogicalKeyboardKey.arrowLeft) {
            reverseKeyboardDirection ? onIncrease() : onDecrease();
            return KeyEventResult.handled;
          }
          return KeyEventResult.ignored;
        },
        child: MouseRegion(
          cursor: SystemMouseCursors.resizeColumn,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onHorizontalDragUpdate: (details) => onDrag(details.delta.dx),
            onDoubleTap: onReset,
            child: SizedBox(
              width: width,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Container(width: 1, color: theme.dividerColor),
                  if (showGrip)
                    Container(
                      width: 6,
                      height: 40,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.outlineVariant,
                        borderRadius: HypatiaTokens.cornersPill,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
