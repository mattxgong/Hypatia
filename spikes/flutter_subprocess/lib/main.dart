import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const SubprocessSpikeApp());
}

class SubprocessSpikeApp extends StatelessWidget {
  const SubprocessSpikeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Spike 0.5.3: Subprocess Management',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      home: const SubprocessPage(),
    );
  }
}

enum BackendStatus { stopped, starting, ready, error }

class SubprocessPage extends StatefulWidget {
  const SubprocessPage({super.key});

  @override
  State<SubprocessPage> createState() => _SubprocessPageState();
}

class _SubprocessPageState extends State<SubprocessPage> {
  BackendStatus _status = BackendStatus.stopped;
  Process? _process;
  String _log = '';
  String _pythonPath = '';
  int _port = 8742;
  Timer? _healthTimer;
  final _logController = ScrollController();

  @override
  void initState() {
    super.initState();
    _discoverPython();
  }

  @override
  void dispose() {
    _killBackend();
    _healthTimer?.cancel();
    _logController.dispose();
    super.dispose();
  }

  void _appendLog(String message) {
    setState(() {
      _log += '${DateTime.now().toIso8601String().substring(11, 19)} $message\n';
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_logController.hasClients &&
          _logController.position.hasContentDimensions) {
        _logController.animateTo(
          _logController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 100),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _discoverPython() async {
    _appendLog('Discovering Python...');

    final candidates = ['python', 'python3', 'py'];

    for (final cmd in candidates) {
      try {
        final result = await Process.run(cmd, ['--version']);
        if (result.exitCode == 0) {
          final version = (result.stdout as String).trim();
          setState(() => _pythonPath = cmd);
          _appendLog('Found Python: $cmd ($version)');
          return;
        }
      } catch (_) {
        // Not found, try next
      }
    }

    // Try common install locations on Windows
    final home = Platform.environment['USERPROFILE'] ?? '';
    final windowsPaths = [
      '$home\\AppData\\Local\\Programs\\Python\\Python313\\python.exe',
      '$home\\AppData\\Local\\Programs\\Python\\Python312\\python.exe',
      '$home\\AppData\\Local\\Programs\\Python\\Python311\\python.exe',
      '$home\\AppData\\Local\\Programs\\Python\\Python310\\python.exe',
      'C:\\Python313\\python.exe',
      'C:\\Python312\\python.exe',
      'C:\\Python311\\python.exe',
    ];

    for (final path in windowsPaths) {
      if (await File(path).exists()) {
        try {
          final result = await Process.run(path, ['--version']);
          if (result.exitCode == 0) {
            final version = (result.stdout as String).trim();
            setState(() => _pythonPath = path);
            _appendLog('Found Python at: $path ($version)');
            return;
          }
        } catch (_) {}
      }
    }

    _appendLog('ERROR: Python not found!');
    setState(() => _status = BackendStatus.error);
  }

  Future<bool> _isPortAvailable(int port) async {
    try {
      final server =
          await ServerSocket.bind(InternetAddress.loopbackIPv4, port);
      await server.close();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _startBackend() async {
    if (_pythonPath.isEmpty) {
      _appendLog('Cannot start: Python not found.');
      return;
    }

    setState(() => _status = BackendStatus.starting);
    _appendLog('Starting backend on port $_port...');

    if (!await _isPortAvailable(_port)) {
      _appendLog('Port $_port is in use, trying ${_port + 1}...');
      _port++;
      if (!await _isPortAvailable(_port)) {
        _appendLog('ERROR: No available port found.');
        setState(() => _status = BackendStatus.error);
        return;
      }
    }

    final backendDir = '${Directory.current.path}${Platform.pathSeparator}backend';
    final serverScript = '$backendDir${Platform.pathSeparator}server.py';

    if (!await File(serverScript).exists()) {
      _appendLog('ERROR: Backend script not found at $serverScript');
      setState(() => _status = BackendStatus.error);
      return;
    }

    try {
      _process = await Process.start(
        _pythonPath,
        [
          '-m',
          'uvicorn',
          'server:app',
          '--host',
          '127.0.0.1',
          '--port',
          '$_port',
        ],
        workingDirectory: backendDir,
      );

      _appendLog('Process started (PID: ${_process!.pid})');

      _process!.stdout.transform(utf8.decoder).listen((data) {
        for (final line in data.trim().split('\n')) {
          _appendLog('[stdout] $line');
        }
      });
      _process!.stderr.transform(utf8.decoder).listen((data) {
        for (final line in data.trim().split('\n')) {
          _appendLog('[stderr] $line');
        }
      });

      _process!.exitCode.then((code) {
        _appendLog('Process exited with code $code');
        if (mounted) {
          setState(() => _status = BackendStatus.stopped);
        }
        _healthTimer?.cancel();
      });

      _startHealthPolling();
    } catch (e) {
      _appendLog('ERROR starting process: $e');
      setState(() => _status = BackendStatus.error);
    }
  }

  void _startHealthPolling() {
    var attempts = 0;
    const maxAttempts = 30;

    _healthTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      attempts++;
      try {
        final response = await http
            .get(Uri.parse('http://127.0.0.1:$_port/health'))
            .timeout(const Duration(seconds: 2));

        if (response.statusCode == 200) {
          final body = jsonDecode(response.body);
          if (body['status'] == 'ok') {
            _appendLog('Health check passed! Backend is ready.');
            setState(() => _status = BackendStatus.ready);
            timer.cancel();

            // Switch to periodic health monitoring
            _healthTimer =
                Timer.periodic(const Duration(seconds: 5), (_) async {
              try {
                await http
                    .get(Uri.parse('http://127.0.0.1:$_port/health'))
                    .timeout(const Duration(seconds: 2));
              } catch (_) {
                _appendLog('Health check failed — backend may have crashed.');
                setState(() => _status = BackendStatus.error);
              }
            });
          }
        }
      } catch (_) {
        if (attempts >= maxAttempts) {
          _appendLog(
              'ERROR: Backend failed to start after $maxAttempts attempts.');
          setState(() => _status = BackendStatus.error);
          timer.cancel();
        }
      }
    });
  }

  Future<void> _killBackend() async {
    _healthTimer?.cancel();
    if (_process != null) {
      _appendLog('Killing backend (PID: ${_process!.pid})...');

      if (Platform.isWindows) {
        // taskkill /T kills the entire process tree
        await Process.run(
            'taskkill', ['/F', '/T', '/PID', '${_process!.pid}']);
      } else {
        _process!.kill(ProcessSignal.sigterm);
      }

      _process = null;
      _appendLog('Backend stopped.');
      setState(() => _status = BackendStatus.stopped);
    }
  }

  Color _statusColor() {
    return switch (_status) {
      BackendStatus.stopped => Colors.grey,
      BackendStatus.starting => Colors.orange,
      BackendStatus.ready => Colors.green,
      BackendStatus.error => Colors.red,
    };
  }

  String _statusText() {
    return switch (_status) {
      BackendStatus.stopped => 'Stopped',
      BackendStatus.starting => 'Starting...',
      BackendStatus.ready => 'Ready',
      BackendStatus.error => 'Error',
    };
  }

  IconData _statusIcon() {
    return switch (_status) {
      BackendStatus.stopped => Icons.stop_circle_outlined,
      BackendStatus.starting => Icons.hourglass_top,
      BackendStatus.ready => Icons.check_circle,
      BackendStatus.error => Icons.error,
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Spike 0.5.3: Flutter Subprocess Management'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  children: [
                    Icon(_statusIcon(), color: _statusColor(), size: 48),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Backend Status: ${_statusText()}',
                            style: Theme.of(context).textTheme.headlineSmall,
                          ),
                          Text(
                              'Python: ${_pythonPath.isEmpty ? "not found" : _pythonPath}'),
                          Text('Port: $_port'),
                          if (_process != null) Text('PID: ${_process!.pid}'),
                        ],
                      ),
                    ),
                    Column(
                      children: [
                        ElevatedButton.icon(
                          onPressed: _status == BackendStatus.stopped ||
                                  _status == BackendStatus.error
                              ? _startBackend
                              : null,
                          icon: const Icon(Icons.play_arrow),
                          label: const Text('Start'),
                        ),
                        const SizedBox(height: 8),
                        ElevatedButton.icon(
                          onPressed: _status == BackendStatus.ready ||
                                  _status == BackendStatus.starting
                              ? _killBackend
                              : null,
                          icon: const Icon(Icons.stop),
                          label: const Text('Stop'),
                          style: ElevatedButton.styleFrom(
                            foregroundColor: Colors.red,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text('Log Output', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Expanded(
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.black87,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: SingleChildScrollView(
                  controller: _logController,
                  child: SelectableText(
                    _log.isEmpty ? 'Waiting...' : _log,
                    style: const TextStyle(
                      fontFamily: 'Consolas',
                      fontSize: 12,
                      color: Colors.greenAccent,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
