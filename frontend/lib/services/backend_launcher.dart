import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';

enum BackendStatus {
  stopped,
  discoveringPython,
  settingUpEnvironment,
  starting,
  ready,
  crashed,
  error,
}

class BackendLauncher {
  BackendLauncher({this.devMode = false, this.externalBaseUrl});

  final bool devMode;
  final String? externalBaseUrl;

  static const _defaultPort = 8000;
  static const _maxPortAttempts = 11;

  Process? _process;
  int _port = _defaultPort;
  String? _pythonPath;
  bool _stopRequested = false;
  bool _restartedAfterCrash = false;
  BackendStatus _status = BackendStatus.stopped;

  final _statusController = StreamController<BackendStatus>.broadcast();
  final _logController = StreamController<String>.broadcast();

  Stream<BackendStatus> get onStatusChange => _statusController.stream;

  Stream<void> get onBackendReady =>
      onStatusChange.where((s) => s == BackendStatus.ready).take(1);

  Stream<String> get onLog => _logController.stream;

  BackendStatus get status => _status;
  int get port => _port;
  String get baseUrl => devMode && externalBaseUrl != null
      ? externalBaseUrl!
      : 'http://127.0.0.1:$_port';

  void _setStatus(BackendStatus status) {
    _status = status;
    _statusController.add(status);
  }

  void _log(String message) {
    _logController.add(message);
  }

  Future<void> startBackend() async {
    _stopRequested = false;

    if (devMode && externalBaseUrl != null) {
      _log('Dev mode: connecting to external backend at $externalBaseUrl');
      _setStatus(BackendStatus.starting);
      final ready = await _pollHealth(maxAttempts: 10);
      _setStatus(ready ? BackendStatus.ready : BackendStatus.error);
      return;
    }

    _setStatus(BackendStatus.discoveringPython);
    _pythonPath = await _loadCachedPythonPath();
    _pythonPath ??= await _discoverPython();
    if (_pythonPath == null) {
      _log('ERROR: Python 3 was not found. Install Python 3.11+ and retry.');
      _setStatus(BackendStatus.error);
      return;
    }
    await _cachePythonPath(_pythonPath!);

    final backendDir = await _findBackendDir();
    if (backendDir == null) {
      _log('ERROR: could not locate the backend directory.');
      _setStatus(BackendStatus.error);
      return;
    }

    _setStatus(BackendStatus.settingUpEnvironment);
    final venvPython = await _ensureVenv(backendDir);
    if (venvPython == null) {
      _setStatus(BackendStatus.error);
      return;
    }

    _port = await _selectPort();
    await _writePortFile(_port);

    _setStatus(BackendStatus.starting);
    final started = await _spawnProcess(venvPython, backendDir);
    if (!started) {
      _setStatus(BackendStatus.error);
      return;
    }

    final ready = await _pollHealth(maxAttempts: 30);
    _setStatus(ready ? BackendStatus.ready : BackendStatus.error);
  }

  Future<void> stopBackend({
    Duration gracePeriod = const Duration(seconds: 5),
  }) async {
    _stopRequested = true;
    final process = _process;
    if (process == null) {
      _setStatus(BackendStatus.stopped);
      return;
    }

    _log('Stopping backend (PID: ${process.pid})...');

    if (Platform.isWindows) {
      await Process.run('taskkill', ['/F', '/T', '/PID', '${process.pid}']);
    } else {
      process.kill(ProcessSignal.sigterm);
      final exited = await process.exitCode
          .timeout(gracePeriod, onTimeout: () => -1)
          .then((_) => true)
          .catchError((_) => false);
      if (!exited) {
        process.kill(ProcessSignal.sigkill);
      }
    }

    _process = null;
    _log('Backend stopped.');
    _setStatus(BackendStatus.stopped);
  }

  Future<bool> isBackendRunning() => _pollHealth(maxAttempts: 1);

  Future<bool> _pollHealth({required int maxAttempts}) async {
    final dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 2),
        receiveTimeout: const Duration(seconds: 2),
      ),
    );
    try {
      for (var attempt = 0; attempt < maxAttempts; attempt++) {
        if (_stopRequested) return false;
        try {
          final response = await dio.get<Map<String, dynamic>>(
            '$baseUrl/health',
          );
          if (response.statusCode == 200 && response.data?['status'] == 'ok') {
            _log('Health check passed.');
            return true;
          }
        } catch (_) {}
        if (attempt < maxAttempts - 1) {
          await Future<void>.delayed(const Duration(seconds: 1));
        }
      }
    } finally {
      dio.close();
    }
    _log(
      'Backend did not respond to health checks after $maxAttempts attempts.',
    );
    return false;
  }

  Future<String?> _discoverPython() async {
    _log('Discovering Python...');

    final candidates = Platform.isWindows
        ? ['py', 'python', 'python3']
        : ['python3', 'python'];
    for (final cmd in candidates) {
      final resolved = await _tryPython(
        cmd,
        Platform.isWindows && cmd == 'py' ? ['-3'] : [],
      );
      if (resolved != null) return resolved;
    }

    final home = Platform.isWindows
        ? Platform.environment['USERPROFILE'] ?? ''
        : Platform.environment['HOME'] ?? '';

    final sep = Platform.pathSeparator;
    final fallbackPaths = Platform.isWindows
        ? [
            for (final v in ['313', '312', '311', '310'])
              [
                home,
                'AppData',
                'Local',
                'Programs',
                'Python',
                'Python$v',
                'python.exe',
              ].join(sep),
            for (final v in ['313', '312', '311', '310'])
              ['C:', 'Python$v', 'python.exe'].join(sep),
          ]
        : [
            '/usr/local/bin/python3',
            '/opt/homebrew/bin/python3',
            '/usr/bin/python3',
          ];

    for (final path in fallbackPaths) {
      if (await File(path).exists()) {
        final resolved = await _tryPython(path, const []);
        if (resolved != null) return resolved;
      }
    }

    return null;
  }

  Future<String?> _tryPython(String executable, List<String> baseArgs) async {
    try {
      final result = await Process.run(executable, [...baseArgs, '--version']);
      if (result.exitCode == 0) {
        final version = '${result.stdout}${result.stderr}'.trim();
        _log('Found Python: $executable $version');
        return baseArgs.isEmpty
            ? executable
            : '$executable ${baseArgs.join(' ')}';
      }
    } catch (_) {}
    return null;
  }

  Future<File> _launcherConfigFile() async {
    final dir = await getApplicationSupportDirectory();
    return File('${dir.path}${Platform.pathSeparator}backend_launcher.json');
  }

  Future<String?> _loadCachedPythonPath() async {
    try {
      final file = await _launcherConfigFile();
      if (!await file.exists()) return null;
      final config =
          jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      final cached = config['pythonPath'] as String?;
      if (cached == null) return null;
      final parts = cached.split(' ');
      if (await _tryPython(parts.first, parts.skip(1).toList()) != null) {
        return cached;
      }
    } catch (_) {}
    return null;
  }

  Future<void> _cachePythonPath(String pythonPath) async {
    try {
      final file = await _launcherConfigFile();
      await file.writeAsString(jsonEncode({'pythonPath': pythonPath}));
    } catch (_) {}
  }

  Future<Directory?> _findBackendDir() async {
    bool hasMarker(Directory dir) => File(
      '${dir.path}${Platform.pathSeparator}app${Platform.pathSeparator}main.py',
    ).existsSync();

    final seen = <String>{};
    final candidates = <Directory>[];
    void add(Directory dir) {
      if (seen.add(dir.path)) candidates.add(dir);
    }

    add(Directory('${Directory.current.path}${Platform.pathSeparator}backend'));

    final exeDir = Directory(File(Platform.resolvedExecutable).parent.path);
    for (final start in [Directory.current, exeDir]) {
      var current = start;
      for (var i = 0; i < 6; i++) {
        add(Directory('${current.path}${Platform.pathSeparator}backend'));
        final parent = current.parent;
        if (parent.path == current.path) break;
        current = parent;
      }
    }

    for (final candidate in candidates) {
      if (hasMarker(candidate)) return candidate;
    }
    return null;
  }

  String _venvPythonPath(Directory backendDir) {
    final venv = '${backendDir.path}${Platform.pathSeparator}.venv';
    return Platform.isWindows
        ? '$venv${Platform.pathSeparator}Scripts${Platform.pathSeparator}python.exe'
        : '$venv${Platform.pathSeparator}bin${Platform.pathSeparator}python';
  }

  Future<String?> _ensureVenv(Directory backendDir) async {
    final venvPython = _venvPythonPath(backendDir);
    if (!await File(venvPython).exists()) {
      _log('Creating Python virtual environment...');
      final parts = _pythonPath!.split(' ');
      final created = await Process.run(parts.first, [
        ...parts.skip(1),
        '-m',
        'venv',
        '.venv',
      ], workingDirectory: backendDir.path);
      if (created.exitCode != 0) {
        _log('ERROR creating venv: ${created.stderr}');
        return null;
      }
    }

    final depsCheck = await Process.run(venvPython, ['-c', 'import fastapi']);
    if (depsCheck.exitCode != 0) {
      _log('Installing backend dependencies (this may take a minute)...');
      final install = await Process.start(venvPython, [
        '-m',
        'pip',
        'install',
        '-r',
        'requirements.txt',
      ], workingDirectory: backendDir.path);
      install.stdout
          .transform(utf8.decoder)
          .listen((data) => _log('[pip] ${data.trim()}'));
      install.stderr
          .transform(utf8.decoder)
          .listen((data) => _log('[pip] ${data.trim()}'));
      final exitCode = await install.exitCode;
      if (exitCode != 0) {
        _log('ERROR: dependency install failed (exit code $exitCode).');
        return null;
      }
    }

    return venvPython;
  }

  Future<bool> _isPortAvailable(int port) async {
    try {
      final server = await ServerSocket.bind(
        InternetAddress.loopbackIPv4,
        port,
      );
      await server.close();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<int> _selectPort() async {
    for (var i = 0; i < _maxPortAttempts; i++) {
      final candidate = _defaultPort + i;
      if (await _isPortAvailable(candidate)) return candidate;
    }
    _log('WARNING: no free port found; defaulting to $_defaultPort.');
    return _defaultPort;
  }

  Future<void> _writePortFile(int port) async {
    try {
      final file = File(
        '${Directory.systemTemp.path}${Platform.pathSeparator}hypatia_backend_port.txt',
      );
      await file.writeAsString('$port');
    } catch (_) {}
  }

  Future<bool> _spawnProcess(String venvPython, Directory backendDir) async {
    try {
      _process = await Process.start(
        venvPython,
        [
          '-m',
          'uvicorn',
          'app.main:app',
          '--host',
          '127.0.0.1',
          '--port',
          '$_port',
        ],
        workingDirectory: backendDir.path,
        runInShell: false,
      );
    } catch (e) {
      _log('ERROR starting backend process: $e');
      return false;
    }

    _log('Backend process started (PID: ${_process!.pid}).');
    _process!.stdout.transform(utf8.decoder).listen((data) {
      for (final line in data.trim().split('\n')) {
        if (line.isNotEmpty) _log('[backend] $line');
      }
    });
    _process!.stderr.transform(utf8.decoder).listen((data) {
      for (final line in data.trim().split('\n')) {
        if (line.isNotEmpty) _log('[backend] $line');
      }
    });

    unawaited(
      _process!.exitCode.then((code) async {
        final wasRequested = _stopRequested;
        _process = null;
        if (wasRequested) return;

        _log('Backend exited unexpectedly (code $code).');
        if (!_restartedAfterCrash) {
          _restartedAfterCrash = true;
          _log('Attempting a single automatic restart...');
          _setStatus(BackendStatus.crashed);
          await startBackend();
        } else {
          _setStatus(BackendStatus.crashed);
        }
      }),
    );

    return true;
  }

  void dispose() {
    _statusController.close();
    _logController.close();
  }
}
