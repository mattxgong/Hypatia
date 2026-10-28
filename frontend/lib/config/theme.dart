import 'package:flutter/material.dart';

/// Colors the Material scheme has no slot for.
@immutable
class StatusColors extends ThemeExtension<StatusColors> {
  const StatusColors({required this.success, required this.onSuccess});

  /// Correct answers, passing checks, a working connection.
  final Color success;
  final Color onSuccess;

  /// The theme's status colors, or defaults for its brightness when the
  /// theme in use (e.g. a dialog's or a test's) doesn't carry them.
  static StatusColors of(BuildContext context) {
    final theme = Theme.of(context);
    return theme.extension<StatusColors>() ??
        (theme.brightness == Brightness.dark
            ? const StatusColors(
                success: Color(0xFFA6E3A1),
                onSuccess: Color(0xFF11111B),
              )
            : const StatusColors(
                success: Color(0xFF2E7D32),
                onSuccess: Colors.white,
              ));
  }

  @override
  StatusColors copyWith({Color? success, Color? onSuccess}) => StatusColors(
    success: success ?? this.success,
    onSuccess: onSuccess ?? this.onSuccess,
  );

  @override
  StatusColors lerp(StatusColors? other, double t) => other == null
      ? this
      : StatusColors(
          success: Color.lerp(success, other.success, t)!,
          onSuccess: Color.lerp(onSuccess, other.onSuccess, t)!,
        );
}

class HypatiaTheme {
  HypatiaTheme._();

  static const _seedColor = Color(0xFF7C4DFF);

  /// The dark palette, as one surface ramp. Sidebar, chat, cards and inputs
  /// all read these slots, so nothing is a one-off hard-coded color that
  /// clashes with the seed-derived rest of the scheme.
  static final _darkScheme =
      ColorScheme.fromSeed(
        seedColor: _seedColor,
        brightness: Brightness.dark,
      ).copyWith(
        surface: const Color(0xFF1E1E2E),
        onSurface: const Color(0xFFCDD6F4),
        surfaceContainerLowest: const Color(0xFF181825),
        surfaceContainerLow: const Color(0xFF232334),
        surfaceContainer: const Color(0xFF2A2A3C),
        surfaceContainerHigh: const Color(0xFF313244),
        surfaceContainerHighest: const Color(0xFF3B3C50),
        outlineVariant: const Color(0xFF45475A),
      );

  static final _lightScheme = ColorScheme.fromSeed(
    seedColor: _seedColor,
    brightness: Brightness.light,
  );

  static final darkTheme = _build(
    _darkScheme,
    const StatusColors(
      success: Color(0xFFA6E3A1),
      onSuccess: Color(0xFF11111B),
    ),
  );

  static final lightTheme = _build(
    _lightScheme,
    const StatusColors(success: Color(0xFF2E7D32), onSuccess: Colors.white),
  );

  static ThemeData _build(ColorScheme scheme, StatusColors status) => ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surfaceContainerLowest,
      foregroundColor: scheme.onSurface,
      elevation: 0,
    ),
    cardTheme: CardThemeData(color: scheme.surfaceContainer, elevation: 0),
    dividerTheme: DividerThemeData(color: scheme.outlineVariant, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHigh,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide.none,
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    extensions: [status],
  );
}
