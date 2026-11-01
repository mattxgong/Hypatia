import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Whether the app is in the foreground. On a phone, polling skips its ticks
/// while the app is in the background, and resumes when it comes back.
final appInForegroundProvider = StateProvider<bool>((ref) => true);
