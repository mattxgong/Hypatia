import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_client.dart';

enum WsConnectionState { disconnected, connecting, connected, reconnecting }

class ChatWsChunk {
  const ChatWsChunk({required this.content});
  final String content;
}

class ChatWsComplete {
  const ChatWsComplete({required this.messageId, this.citations, this.result});
  final String messageId;
  final List<dynamic>? citations;
  final Map<String, dynamic>? result;
}

class ChatWsProgress {
  const ChatWsProgress({
    required this.operation,
    required this.operationId,
    required this.percent,
    required this.message,
  });
  final String operation;
  final String operationId;
  final int percent;
  final String message;
}

class ChatWsError {
  const ChatWsError({required this.message, this.code});
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

  final _stateController = StreamController<WsConnectionState>.broadcast();
  final _chunkController = StreamController<ChatWsChunk>.broadcast();
  final _completeController = StreamController<ChatWsComplete>.broadcast();
  final _progressController = StreamController<ChatWsProgress>.broadcast();
  final _errorController = StreamController<ChatWsError>.broadcast();

  WsConnectionState _state = WsConnectionState.disconnected;

  WsConnectionState get state => _state;
  Stream<WsConnectionState> get onStateChange => _stateController.stream;
  Stream<ChatWsChunk> get onChunk => _chunkController.stream;
  Stream<ChatWsComplete> get onComplete => _completeController.stream;
  Stream<ChatWsProgress> get onProgress => _progressController.stream;
  Stream<ChatWsError> get onError => _errorController.stream;

  void _setState(WsConnectionState newState) {
    _state = newState;
    _stateController.add(newState);
  }

  Future<void> connect(String classId) async {
    if (_currentClassId == classId && _state == WsConnectionState.connected) {
      return;
    }

    await disconnect();
    _currentClassId = classId;
    _setState(WsConnectionState.connecting);

    try {
      final url = apiClient.getChatWebSocketUrl(classId);
      _channel = WebSocketChannel.connect(Uri.parse(url));
      await _channel!.ready;
      _reconnectAttempts = 0;
      _setState(WsConnectionState.connected);
      _subscription = _channel!.stream.listen(
        _handleMessage,
        onDone: _handleDisconnect,
        onError: (_) => _handleDisconnect(),
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void sendMessage(String content) {
    if (_state != WsConnectionState.connected || _channel == null) return;
    _channel!.sink.add(jsonEncode({'type': 'message', 'content': content}));
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
    final data = jsonDecode(raw as String) as Map<String, dynamic>;
    final type = data['type'] as String;

    switch (type) {
      case 'chunk':
        _chunkController.add(ChatWsChunk(content: data['content'] as String));
      case 'complete':
        _completeController.add(
          ChatWsComplete(
            messageId: data['message_id'] as String,
            citations: data['citations'] as List<dynamic>?,
            result: data['result'] as Map<String, dynamic>?,
          ),
        );
      case 'progress':
        _progressController.add(
          ChatWsProgress(
            operation: data['operation'] as String,
            operationId: data['operation_id'] as String,
            percent: data['percent'] as int,
            message: data['message'] as String,
          ),
        );
      case 'error':
        _errorController.add(
          ChatWsError(
            message: data['message'] as String,
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
    disconnect();
    _stateController.close();
    _chunkController.close();
    _completeController.close();
    _progressController.close();
    _errorController.close();
  }
}
