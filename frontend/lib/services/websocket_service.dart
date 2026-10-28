import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_client.dart';

enum WsConnectionState { disconnected, connecting, connected, reconnecting }

// Every event carries the Class whose socket it arrived on. The one socket
// follows the active Class, so listeners must ignore other Classes' events.

class ChatWsChunk {
  const ChatWsChunk({required this.classId, required this.content});
  final String classId;
  final String content;
}

class ChatWsComplete {
  const ChatWsComplete({
    required this.classId,
    required this.messageId,
    this.content,
    this.citations,
    this.result,
  });
  final String classId;
  final String messageId;
  final String? content;
  final List<dynamic>? citations;
  final Map<String, dynamic>? result;
}

class ChatWsProgress {
  const ChatWsProgress({
    required this.classId,
    required this.operation,
    required this.operationId,
    required this.percent,
    required this.message,
  });
  final String classId;
  final String operation;
  final String operationId;
  final int? percent;
  final String message;
}

class ChatWsError {
  const ChatWsError({required this.classId, required this.message, this.code});
  final String classId;
  final String message;
  final String? code;
}

final webSocketServiceProvider = Provider<WebSocketService>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  final service = WebSocketService(apiClient: apiClient);
  ref.onDispose(() => service.dispose());
  return service;
});

class WebSocketService {
  WebSocketService({required this.apiClient});

  final ApiClient apiClient;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  String? _currentClassId;
  int _reconnectAttempts = 0;
  Timer? _reconnectTimer;

  // Synchronous, so a listener checking isConnectedTo() sees the state as of
  // this event, not after a quick disconnect-reconnect has already happened.
  final _stateController = StreamController<WsConnectionState>.broadcast(
    sync: true,
  );
  final _chunkController = StreamController<ChatWsChunk>.broadcast();
  final _completeController = StreamController<ChatWsComplete>.broadcast();
  final _progressController = StreamController<ChatWsProgress>.broadcast();
  final _errorController = StreamController<ChatWsError>.broadcast();

  WsConnectionState _state = WsConnectionState.disconnected;

  WsConnectionState get state => _state;

  /// The Class the socket is connected (or reconnecting) to, if any.
  String? get currentClassId => _currentClassId;

  bool isConnectedTo(String classId) =>
      _state == WsConnectionState.connected && _currentClassId == classId;
  Stream<WsConnectionState> get onStateChange => _stateController.stream;
  Stream<ChatWsChunk> get onChunk => _chunkController.stream;
  Stream<ChatWsComplete> get onComplete => _completeController.stream;
  Stream<ChatWsProgress> get onProgress => _progressController.stream;
  Stream<ChatWsError> get onError => _errorController.stream;

  // Set by dispose(); the async tail of disconnect() and any pending
  // reconnect must not touch the closed streams afterwards.
  bool _disposed = false;

  void _setState(WsConnectionState newState) {
    if (_disposed) return;
    _state = newState;
    _stateController.add(newState);
  }

  Future<void> connect(String classId) async {
    if (_disposed) return;
    if (_currentClassId == classId && _state == WsConnectionState.connected) {
      return;
    }

    await disconnect();
    _currentClassId = classId;
    _setState(WsConnectionState.connecting);

    try {
      final url = apiClient.getChatWebSocketUrl(classId);
      final channel = IOWebSocketChannel.connect(
        Uri.parse(url),
        headers: apiClient.authHeaders,
      );
      _channel = channel;
      await channel.ready;
      // A newer connect() (the user switched Class) replaced this channel
      // while it was opening.
      if (_channel != channel) return;
      _reconnectAttempts = 0;
      _setState(WsConnectionState.connected);
      _subscription = channel.stream.listen(
        _handleMessage,
        onDone: _handleDisconnect,
        onError: (_) => _handleDisconnect(),
      );
    } catch (_) {
      if (_currentClassId == classId) _scheduleReconnect();
    }
  }

  /// Sends [content] to [classId]'s chat. Returns false (sending nothing)
  /// unless the socket is currently connected to that Class.
  bool sendMessage(String classId, String content) {
    if (!isConnectedTo(classId) || _channel == null) return false;
    _channel!.sink.add(jsonEncode({'type': 'message', 'content': content}));
    return true;
  }

  void cancelOperation(String operationId) {
    if (_state != WsConnectionState.connected || _channel == null) return;
    _channel!.sink.add(
      jsonEncode({'type': 'cancel', 'operation_id': operationId}),
    );
  }

  Future<void> disconnect() async {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _currentClassId = null;
    await _subscription?.cancel();
    _subscription = null;
    await _channel?.sink.close();
    _channel = null;
    _setState(WsConnectionState.disconnected);
  }

  void _handleMessage(dynamic raw) {
    final classId = _currentClassId;
    if (classId == null) return;
    final Map<String, dynamic> data;
    try {
      data = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (_) {
      return;
    }

    switch (data['type']) {
      case 'chunk':
        _chunkController.add(
          ChatWsChunk(
            classId: classId,
            content: data['content'] as String? ?? '',
          ),
        );
      case 'complete':
        _completeController.add(
          ChatWsComplete(
            classId: classId,
            messageId: data['message_id'] as String? ?? '',
            content: data['content'] as String?,
            citations: data['citations'] as List<dynamic>?,
            result: data['result'] as Map<String, dynamic>?,
          ),
        );
      case 'progress':
        _progressController.add(
          ChatWsProgress(
            classId: classId,
            operation: data['operation'] as String? ?? 'operation',
            operationId: data['operation_id'] as String? ?? '',
            percent: (data['percent'] as num?)?.toInt(),
            message: data['message'] as String? ?? '',
          ),
        );
      case 'error':
        _errorController.add(
          ChatWsError(
            classId: classId,
            message: data['message'] as String? ?? 'Unknown error',
            code: data['code'] as String?,
          ),
        );
    }
  }

  void _handleDisconnect() {
    if (_currentClassId != null) {
      _scheduleReconnect();
    } else {
      _setState(WsConnectionState.disconnected);
    }
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _setState(WsConnectionState.reconnecting);
    _reconnectAttempts++;
    final delay = Duration(
      milliseconds: (1000 * (1 << _reconnectAttempts.clamp(0, 5))),
    );
    _reconnectTimer = Timer(delay, () {
      if (_currentClassId != null) {
        connect(_currentClassId!);
      }
    });
  }

  void dispose() {
    _disposed = true;
    unawaited(disconnect());
    _stateController.close();
    _chunkController.close();
    _completeController.close();
    _progressController.close();
    _errorController.close();
  }
}
