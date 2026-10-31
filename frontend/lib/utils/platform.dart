import 'package:flutter/foundation.dart';

/// Windows, macOS or Linux: the platforms that run the backend themselves and
/// have desktop-only features such as drag and drop from the file manager.
bool get isDesktop =>
    !kIsWeb &&
    (defaultTargetPlatform == TargetPlatform.windows ||
        defaultTargetPlatform == TargetPlatform.macOS ||
        defaultTargetPlatform == TargetPlatform.linux);
