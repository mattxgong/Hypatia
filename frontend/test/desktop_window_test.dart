import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/services/backend_launcher.dart';
import 'package:frontend/services/desktop_window.dart';

void main() {
  group('closing the window', () {
    test('quits while remote access is off', () {
      for (final platform in [TargetPlatform.windows, TargetPlatform.linux]) {
        expect(
          closeAction(
            remoteAccessOn: false,
            trayShown: false,
            platform: platform,
          ),
          CloseAction.quit,
        );
      }
    });

    test('hides to the tray while remote access is on', () {
      expect(
        closeAction(
          remoteAccessOn: true,
          trayShown: true,
          platform: TargetPlatform.windows,
        ),
        CloseAction.hide,
      );
      expect(
        closeAction(
          remoteAccessOn: true,
          trayShown: true,
          platform: TargetPlatform.macOS,
        ),
        CloseAction.hide,
      );
    });

    test('minimizes on Linux, where the tray icon may be invisible', () {
      expect(
        closeAction(
          remoteAccessOn: true,
          trayShown: true,
          platform: TargetPlatform.linux,
        ),
        CloseAction.minimize,
      );
    });

    test('quits when no tray icon could be shown', () {
      expect(
        closeAction(
          remoteAccessOn: true,
          trayShown: false,
          platform: TargetPlatform.windows,
        ),
        CloseAction.quit,
      );
    });
  });

  test('the tray menu offers open, pair and quit, with the port', () {
    final menu = trayMenu(const RemoteAccess(enabled: true, port: 9000));
    final items = menu.items!.where((i) => i.key != null).toList();

    expect(items.map((i) => i.key), ['open', 'pair', 'status', 'quit']);
    final status = items.firstWhere((i) => i.key == 'status');
    expect(status.label, 'Phones can connect on port 9000');
    expect(status.disabled, isTrue);
  });
}
