import 'package:flutter/material.dart';

/// The design slots the Material scheme lacks: text levels, lines, the accent
/// tint, status colors and elevation. Widgets read these instead of picking
/// colors, radii or shadows themselves, so every layout shares one look.
///
/// The violet seed is the only strong color; everything else is neutral.
@immutable
class HypatiaTokens extends ThemeExtension<HypatiaTokens> {
  const HypatiaTokens({
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.hairline,
    required this.strongBorder,
    required this.accentTint,
    required this.success,
    required this.onSuccess,
    required this.warning,
    required this.danger,
    required this.shadowLow,
    required this.shadowMid,
    required this.shadowHigh,
  });

  /// Derives every slot from [scheme], plus the status colors it has no slot for.
  factory HypatiaTokens.from(ColorScheme scheme) {
    final dark = scheme.brightness == Brightness.dark;
    List<BoxShadow> shadow(double blur, double y, double alpha) => [
      BoxShadow(
        color: Colors.black.withValues(alpha: dark ? alpha * 2 : alpha),
        blurRadius: blur,
        offset: Offset(0, y),
      ),
    ];
    return HypatiaTokens(
      textPrimary: scheme.onSurface,
      textSecondary: scheme.onSurfaceVariant,
      textMuted: scheme.onSurface.withValues(alpha: 0.55),
      hairline: scheme.outlineVariant,
      strongBorder: scheme.outline,
      accentTint: scheme.primary.withValues(alpha: dark ? 0.18 : 0.10),
      success: dark ? const Color(0xFFA6E3A1) : const Color(0xFF2E7D32),
      onSuccess: dark ? const Color(0xFF11111B) : Colors.white,
      warning: dark ? const Color(0xFFF9E2AF) : const Color(0xFFB26A00),
      danger: scheme.error,
      shadowLow: shadow(2, 1, 0.08),
      shadowMid: shadow(8, 2, 0.10),
      shadowHigh: shadow(24, 8, 0.14),
    );
  }

  /// One base radius; the others derive from it.
  static const double radius = 10;
  static const double radiusSmall = radius * 0.6;
  static const double radiusLarge = radius * 1.6;
  static const double radiusPill = 999;

  static final BorderRadius corners = BorderRadius.circular(radius);
  static final BorderRadius cornersSmall = BorderRadius.circular(radiusSmall);
  static final BorderRadius cornersLarge = BorderRadius.circular(radiusLarge);
  static final BorderRadius cornersPill = BorderRadius.circular(radiusPill);

  /// Whether controls should be finger-sized: true on Android and iOS, where
  /// the theme pads tap targets to 48 dp, and false on desktop, which keeps
  /// the compact sizes a mouse can hit.
  static bool touch(BuildContext context) =>
      Theme.of(context).materialTapTargetSize == MaterialTapTargetSize.padded;

  /// Minimum size for a small icon button: [desktop] with a mouse, 48 dp on a
  /// touch screen.
  static BoxConstraints iconButtonSize(BuildContext context, double desktop) {
    final size = touch(context) ? kMinInteractiveDimension : desktop;
    return BoxConstraints(minWidth: size, minHeight: size);
  }

  /// Body text, headings.
  final Color textPrimary;

  /// Labels, secondary lines.
  final Color textSecondary;

  /// Hints, timestamps, disabled text.
  final Color textMuted;

  /// Dividers and quiet outlines.
  final Color hairline;

  /// Outlines that must stay visible, e.g. a focused or selected item.
  final Color strongBorder;

  /// The seed color at low opacity: selected rows, pills.
  final Color accentTint;

  /// Correct answers, passing checks, a working connection.
  final Color success;
  final Color onSuccess;
  final Color warning;
  final Color danger;

  /// Resting cards, raised controls, floating overlays.
  final List<BoxShadow> shadowLow;
  final List<BoxShadow> shadowMid;
  final List<BoxShadow> shadowHigh;

  /// The theme's tokens, or ones derived from its scheme when the theme in
  /// use (e.g. a dialog's or a test's) doesn't carry them.
  static HypatiaTokens of(BuildContext context) {
    final theme = Theme.of(context);
    return theme.extension<HypatiaTokens>() ??
        HypatiaTokens.from(theme.colorScheme);
  }

  @override
  HypatiaTokens copyWith({
    Color? textPrimary,
    Color? textSecondary,
    Color? textMuted,
    Color? hairline,
    Color? strongBorder,
    Color? accentTint,
    Color? success,
    Color? onSuccess,
    Color? warning,
    Color? danger,
    List<BoxShadow>? shadowLow,
    List<BoxShadow>? shadowMid,
    List<BoxShadow>? shadowHigh,
  }) => HypatiaTokens(
    textPrimary: textPrimary ?? this.textPrimary,
    textSecondary: textSecondary ?? this.textSecondary,
    textMuted: textMuted ?? this.textMuted,
    hairline: hairline ?? this.hairline,
    strongBorder: strongBorder ?? this.strongBorder,
    accentTint: accentTint ?? this.accentTint,
    success: success ?? this.success,
    onSuccess: onSuccess ?? this.onSuccess,
    warning: warning ?? this.warning,
    danger: danger ?? this.danger,
    shadowLow: shadowLow ?? this.shadowLow,
    shadowMid: shadowMid ?? this.shadowMid,
    shadowHigh: shadowHigh ?? this.shadowHigh,
  );

  @override
  HypatiaTokens lerp(HypatiaTokens? other, double t) {
    if (other == null) return this;
    Color c(Color a, Color b) => Color.lerp(a, b, t)!;
    List<BoxShadow> s(List<BoxShadow> a, List<BoxShadow> b) =>
        BoxShadow.lerpList(a, b, t)!;
    return HypatiaTokens(
      textPrimary: c(textPrimary, other.textPrimary),
      textSecondary: c(textSecondary, other.textSecondary),
      textMuted: c(textMuted, other.textMuted),
      hairline: c(hairline, other.hairline),
      strongBorder: c(strongBorder, other.strongBorder),
      accentTint: c(accentTint, other.accentTint),
      success: c(success, other.success),
      onSuccess: c(onSuccess, other.onSuccess),
      warning: c(warning, other.warning),
      danger: c(danger, other.danger),
      shadowLow: s(shadowLow, other.shadowLow),
      shadowMid: s(shadowMid, other.shadowMid),
      shadowHigh: s(shadowHigh, other.shadowHigh),
    );
  }
}

/// LLM providers' brand colors, for their icons only.
abstract final class ProviderBrandColors {
  static Color of(String providerId, ThemeData theme) {
    final dark = theme.brightness == Brightness.dark;
    return switch (providerId) {
      'copilot' => dark ? const Color(0xFF79C0FF) : const Color(0xFF24292F),
      'anthropic' => const Color(0xFFD97706),
      'openai' => const Color(0xFF10A37F),
      'ollama' => dark ? Colors.white70 : const Color(0xFF333333),
      'copilot-ollama' => theme.colorScheme.secondary,
      _ => theme.colorScheme.onSurface,
    };
  }
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

  static final darkTheme = _build(_darkScheme);

  static final lightTheme = _build(_lightScheme);

  static ThemeData _build(ColorScheme scheme) {
    final tokens = HypatiaTokens.from(scheme);
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: scheme.surface,
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surfaceContainerLowest,
        foregroundColor: scheme.onSurface,
        elevation: 0,
      ),
      cardTheme: CardThemeData(
        color: scheme.surfaceContainer,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: HypatiaTokens.corners),
      ),
      dialogTheme: DialogThemeData(
        shape: RoundedRectangleBorder(borderRadius: HypatiaTokens.cornersLarge),
      ),
      dividerTheme: DividerThemeData(color: tokens.hairline, thickness: 1),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHigh,
        border: OutlineInputBorder(
          borderRadius: HypatiaTokens.corners,
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 10,
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: HypatiaTokens.corners),
      ),
      extensions: [tokens],
    );
  }
}
