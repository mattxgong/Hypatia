import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/models/chat_message.dart';
import 'package:frontend/providers/chat_provider.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/services/websocket_service.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(baseUrl: 'http://test');

  final historyCalls = <String>[];

  @override
  Future<List<ChatMessage>> getChatHistory(
    String classId, {
    int limit = 50,
    int offset = 0,
  }) async {
    historyCalls.add(classId);
    return [];
  }
}

/// A socket that follows connect() like the real one, without a network.
class _FakeSocket extends WebSocketService {
  _FakeSocket({required super.apiClient});

  final chunks = StreamController<ChatWsChunk>.broadcast();
  final completes = StreamController<ChatWsComplete>.broadcast();
  final states = StreamController<WsConnectionState>.broadcast(sync: true);
  final sent = <(String, String)>[];
  String? connectedTo;
  final connectCalls = <String>[];

  @override
  Stream<ChatWsChunk> get onChunk => chunks.stream;
  @override
  Stream<ChatWsComplete> get onComplete => completes.stream;
  @override
  Stream<ChatWsProgress> get onProgress => const Stream.empty();
  @override
  Stream<ChatWsError> get onError => const Stream.empty();
  @override
  Stream<WsConnectionState> get onStateChange => states.stream;

  @override
  String? get currentClassId => connectedTo;

  @override
  bool isConnectedTo(String classId) => connectedTo == classId;

  @override
  Future<void> connect(String classId) async {
    connectCalls.add(classId);
    setConnected(classId);
  }

  void setConnected(String? classId) {
    connectedTo = classId;
    states.add(
      classId == null
          ? WsConnectionState.disconnected
          : WsConnectionState.connected,
    );
  }

  @override
  bool sendMessage(String classId, String content) {
    if (!isConnectedTo(classId)) return false;
    sent.add((classId, content));
    return true;
  }

  void closeStreams() {
    chunks.close();
    completes.close();
    states.close();
  }

  @override
  void dispose() {}
}

void main() {
  late _FakeApi api;
  late _FakeSocket socket;
  late ProviderContainer container;

  setUp(() {
    api = _FakeApi();
    socket = _FakeSocket(apiClient: api);
    container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        webSocketServiceProvider.overrideWithValue(socket),
      ],
    );
    addTearDown(container.dispose);
    addTearDown(socket.closeStreams);
  });

  Future<void> switchTo(String classId) async {
    container.read(currentClassIdProvider.notifier).state = classId;
    container.read(chatConnectionProvider);
    await container.read(chatMessagesProvider(classId).future);
    await Future<void>.delayed(Duration.zero);
  }

  test('switching back to a Class reconnects the socket to it', () async {
    final sub = container.listen(chatConnectionProvider, (_, _) {});
    addTearDown(sub.close);

    await switchTo('a');
    await switchTo('b');
    await switchTo('a');

    expect(socket.connectCalls, ['a', 'b', 'a']);
    expect(socket.connectedTo, 'a');
  });

  test('a message goes to its own Class, never the connected one', () async {
    await switchTo('a');
    socket.setConnected('b');
    await Future<void>.delayed(Duration.zero);

    final sent = container
        .read(chatMessagesProvider('a').notifier)
        .sendMessage('hello');

    expect(sent, isFalse);
    expect(socket.sent, isEmpty);
    final messages = container.read(chatMessagesProvider('a')).value!;
    expect(messages.single.role, ChatRole.system);
    expect(messages.single.content, contains('not sent'));
  });

  test('frames for another Class are ignored', () async {
    await switchTo('a');
    await container.read(chatMessagesProvider('b').future);

    socket.chunks.add(const ChatWsChunk(classId: 'b', content: 'for b'));
    socket.completes.add(
      const ChatWsComplete(classId: 'b', messageId: 'm1', content: 'for b'),
    );
    await Future<void>.delayed(Duration.zero);

    expect(container.read(chatMessagesProvider('a')).value, isEmpty);
    expect(container.read(chatStreamingContentProvider('a')), isEmpty);
    expect(
      container.read(chatMessagesProvider('b')).value!.single.content,
      'for b',
    );
  });

  test('a disconnect clears a half-streamed reply', () async {
    await switchTo('a');
    socket.chunks.add(const ChatWsChunk(classId: 'a', content: 'partial'));
    await Future<void>.delayed(Duration.zero);
    expect(container.read(chatStreamingContentProvider('a')), 'partial');

    socket.setConnected(null);
    await Future<void>.delayed(Duration.zero);

    expect(container.read(chatStreamingContentProvider('a')), isEmpty);
  });

  test('reconnecting reloads history', () async {
    await switchTo('a');
    final before = api.historyCalls.length;

    socket.setConnected(null);
    socket.setConnected('a');
    await Future<void>.delayed(Duration.zero);

    expect(api.historyCalls.length, before + 1);
  });
}
