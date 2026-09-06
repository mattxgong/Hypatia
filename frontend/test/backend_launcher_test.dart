import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/services/backend_launcher.dart';

void main() {
  group('BackendLauncher external backend configuration', () {
    test('connects without taking ownership of the external process', () async {
      final requests = <String>[];
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((request) async {
        requests.add(request.uri.path);
        request.response.headers.contentType = ContentType.json;
        request.response.write('{"status":"ok"}');
        await request.response.close();
      });
      final launcher = BackendLauncher(
        externalBaseUrl: 'http://127.0.0.1:${server.port}',
      );
      addTearDown(() async {
        launcher.dispose();
        await server.close(force: true);
      });

      await launcher.startBackend();
      expect(launcher.status, BackendStatus.ready);

      await launcher.stopBackend();
      expect(launcher.status, BackendStatus.stopped);
      expect(requests, ['/health']);
    });

    test('uses the configured external backend instead of an owned port', () {
      final launcher = BackendLauncher(
        externalBaseUrl: '  http://127.0.0.1:8123/  ',
      );
      addTearDown(launcher.dispose);

      expect(launcher.externalBaseUrl, 'http://127.0.0.1:8123');
      expect(launcher.baseUrl, 'http://127.0.0.1:8123');
    });

    test('treats an empty external backend URL as automatic mode', () {
      final launcher = BackendLauncher(externalBaseUrl: '   ');
      addTearDown(launcher.dispose);

      expect(launcher.externalBaseUrl, isNull);
      expect(launcher.baseUrl, 'http://127.0.0.1:8000');
    });
  });

  group('BackendLauncher.isSupportedPythonVersion', () {
    test('accepts Python 3.11 and newer', () {
      expect(BackendLauncher.isSupportedPythonVersion('Python 3.11.0'), isTrue);
      expect(BackendLauncher.isSupportedPythonVersion('Python 3.13.7'), isTrue);
      expect(BackendLauncher.isSupportedPythonVersion('Python 4.0.0'), isTrue);
    });

    test('rejects unsupported or malformed versions', () {
      expect(
        BackendLauncher.isSupportedPythonVersion('Python 3.10.14'),
        isFalse,
      );
      expect(
        BackendLauncher.isSupportedPythonVersion('Python 2.7.18'),
        isFalse,
      );
      expect(BackendLauncher.isSupportedPythonVersion('not python'), isFalse);
    });
  });

  group('BackendLauncher.splitPythonCommand', () {
    test('preserves an executable path containing spaces', () {
      const path = r'C:\Program Files\Python311\python.exe';

      expect(
        BackendLauncher.splitPythonCommand(
          path,
          pathExists: (candidate) => candidate == path,
        ),
        [path],
      );
    });

    test('separates launcher arguments', () {
      expect(
        BackendLauncher.splitPythonCommand('py -3', pathExists: (_) => false),
        ['py', '-3'],
      );
    });
  });

  group('BackendLauncher.resolveBackendDirectory', () {
    test('finds backend in a development checkout', () {
      final checkout = Directory.systemTemp.createTempSync('hypatia-dev-');
      addTearDown(() => checkout.deleteSync(recursive: true));
      final backend = Directory(
        '${checkout.path}${Platform.pathSeparator}backend',
      );
      File(
        '${backend.path}${Platform.pathSeparator}app${Platform.pathSeparator}main.py',
      ).createSync(recursive: true);

      final resolved = BackendLauncher.resolveBackendDirectory(
        workingDirectory: checkout,
        executable: File(
          '${checkout.path}${Platform.pathSeparator}frontend${Platform.pathSeparator}build${Platform.pathSeparator}hypatia',
        ),
      );

      expect(resolved?.path, backend.path);
    });

    test('finds backend beside a packaged desktop artifact', () {
      final release = Directory.systemTemp.createTempSync('hypatia-release-');
      addTearDown(() => release.deleteSync(recursive: true));
      final backend = Directory(
        '${release.path}${Platform.pathSeparator}backend',
      );
      File(
        '${backend.path}${Platform.pathSeparator}app${Platform.pathSeparator}main.py',
      ).createSync(recursive: true);
      final executable = File(
        [
          release.path,
          'Hypatia.app',
          'Contents',
          'MacOS',
          'Hypatia',
        ].join(Platform.pathSeparator),
      );

      final resolved = BackendLauncher.resolveBackendDirectory(
        workingDirectory: Directory(
          '${release.path}${Platform.pathSeparator}unrelated',
        ),
        executable: executable,
      );

      expect(resolved?.path, backend.path);
    });
  });
}
