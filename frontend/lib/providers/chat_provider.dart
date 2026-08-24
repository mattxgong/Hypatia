import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/chat_message.dart';
import '../services/api_client.dart';
import '../services/websocket_service.dart';
import 'class_provider.dart';
import 'file_provider.dart';
import 'wiki_provider.dart';

final chatMessagesProvider =
    AsyncNotifierProvider.family<
      ChatMessagesNotifier,
      List<ChatMessage>,
      String
    >(ChatMessagesNotifier.new);

final chatStreamingContentProvider = StateProvider<String>((ref) => '');

final chatInputProvider = StateProvider<String>((ref) => '');

class ChatMessagesNotifier
    extends FamilyAsyncNotifier<List<ChatMessage>, String> {
  StreamSubscription<ChatWsChunk>? _chunkSub;
  StreamSubscription<ChatWsComplete>? _completeSub;
  StreamSubscription<ChatWsError>? _errorSub;

  @override
  Future<List<ChatMessage>> build(String arg) async {
    final apiClient = ref.read(apiClientProvider);
    final messages = await apiClient.getChatHistory(arg);

    final ws = ref.read(webSocketServiceProvider);
    await ws.connect(arg);

    await _chunkSub?.cancel();
    await _completeSub?.cancel();
    await _errorSub?.cancel();

    _chunkSub = ws.onChunk.listen((chunk) {
      final current = ref.read(chatStreamingContentProvider);
      ref.read(chatStreamingContentProvider.notifier).state =
          current + chunk.content;
    });

    _completeSub = ws.onComplete.listen((complete) {
      final streamedContent = ref.read(chatStreamingContentProvider);
      ref.read(chatStreamingContentProvider.notifier).state = '';

      final now = DateTime.now();
      final message = ChatMessage(
        id: complete.messageId,
        classId: arg,
        role: ChatRole.assistant,
        content: streamedContent,
        createdAt: now,
        updatedAt: now,
      );
      state = AsyncData([...state.valueOrNull ?? [], message]);

      _refreshAfterCommand(complete.result);
    });

    _errorSub = ws.onError.listen((error) {
      final now = DateTime.now();
      final message = ChatMessage(
        id: 'error-${now.millisecondsSinceEpoch}',
        classId: arg,
        role: ChatRole.system,
        content: 'Error: ${error.message}',
        createdAt: now,
        updatedAt: now,
      );
      ref.read(chatStreamingContentProvider.notifier).state = '';
      state = AsyncData([...state.valueOrNull ?? [], message]);
    });

    ref.onDispose(() {
      _chunkSub?.cancel();
      _completeSub?.cancel();
      _errorSub?.cancel();
    });

    return messages;
  }

  void sendMessage(String content) {
    final classId = ref.read(currentClassIdProvider);
    if (classId == null) return;

    final now = DateTime.now();
    final userMessage = ChatMessage(
      id: 'local-${now.millisecondsSinceEpoch}',
      classId: classId,
      role: ChatRole.user,
      content: content,
      command: content.startsWith('/') ? content.split(' ').first : null,
      createdAt: now,
      updatedAt: now,
    );
    state = AsyncData([...state.valueOrNull ?? [], userMessage]);

    final ws = ref.read(webSocketServiceProvider);
    ws.sendMessage(content);
  }

  Future<void> clearHistory() async {
    final apiClient = ref.read(apiClientProvider);
    await apiClient.clearChatHistory(arg);
    state = const AsyncData([]);
  }

  void _refreshAfterCommand(Map<String, dynamic>? result) {
    if (result == null) return;
    final command = result['command'] as String?;
    if (command == null) return;

    switch (command) {
      case '/summarize':
        ref.invalidate(wikiTreeProvider(arg));
      case '/remove':
        ref.invalidate(wikiTreeProvider(arg));
        ref.invalidate(fileListProvider(arg));
      case '/rebuild':
        ref.invalidate(wikiTreeProvider(arg));
      case '/lint':
      case '/export':
        break;
    }
  }
}
