import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/chat_message.dart';
import '../services/api_client.dart';
import '../services/websocket_service.dart';
import 'class_provider.dart';
import 'file_provider.dart';
import 'study_provider.dart';
import 'task_provider.dart';
import 'wiki_provider.dart';

final chatMessagesProvider =
    AsyncNotifierProvider.family<
      ChatMessagesNotifier,
      List<ChatMessage>,
      String
    >(ChatMessagesNotifier.new);

/// In-progress assistant text (or progress line) for each Class's chat.
final chatStreamingContentProvider = StateProvider.family<String, String>(
  (ref, classId) => '',
);

/// Keeps the one chat socket connected to the active Class. Watched by the
/// chat panel; switching Class (or back) reconnects to the new one.
final chatConnectionProvider = Provider<void>((ref) {
  final classId = ref.watch(currentClassIdProvider);
  final ws = ref.watch(webSocketServiceProvider);
  // Deferred: connect() changes socket state, whose listeners update other
  // providers, which Riverpod forbids while this provider is building.
  if (classId != null) Future.microtask(() => ws.connect(classId));
});

final chatInputProvider = StateProvider<String>((ref) => '');

/// Bumped to move keyboard focus to the chat input without changing its text.
final chatInputFocusRequestProvider = StateProvider<int>((ref) => 0);

/// The long-running operation (/rebuild, /flashcards, ...) a Class's chat is
/// following, if any; Stop cancels it.
final chatActiveOperationProvider = StateProvider.family<String?, String>(
  (ref, classId) => null,
);

/// Whether a Class's chat has sent something and is waiting for its reply.
final chatAwaitingReplyProvider = StateProvider.family<bool, String>(
  (ref, classId) => false,
);

class ChatMessagesNotifier
    extends FamilyAsyncNotifier<List<ChatMessage>, String> {
  StreamSubscription<ChatWsChunk>? _chunkSub;
  StreamSubscription<ChatWsComplete>? _completeSub;
  StreamSubscription<ChatWsProgress>? _progressSub;
  StreamSubscription<ChatWsError>? _errorSub;

  StreamSubscription<WsConnectionState>? _stateSub;

  StateController<String> get _streaming =>
      ref.read(chatStreamingContentProvider(arg).notifier);

  /// The reply is over (complete, failed or cut off): nothing is pending.
  void _settle() {
    _streaming.state = '';
    ref.read(chatActiveOperationProvider(arg).notifier).state = null;
    ref.read(chatAwaitingReplyProvider(arg).notifier).state = false;
  }

  @override
  Future<List<ChatMessage>> build(String arg) async {
    // Watched, not read: a backend restart replaces the ApiClient and the
    // socket service, and this notifier must resubscribe to the new ones.
    final apiClient = ref.watch(apiClientProvider);
    final ws = ref.watch(webSocketServiceProvider);

    await _chunkSub?.cancel();
    await _completeSub?.cancel();
    await _progressSub?.cancel();
    await _errorSub?.cancel();
    await _stateSub?.cancel();

    _chunkSub = ws.onChunk.where((e) => e.classId == arg).listen((chunk) {
      _streaming.state = _streaming.state + chunk.content;
    });

    _completeSub = ws.onComplete.where((e) => e.classId == arg).listen((
      complete,
    ) {
      final streamedContent = _streaming.state;
      _settle();

      final content = complete.content ?? streamedContent;
      if (content.isNotEmpty) {
        final now = DateTime.now();
        final message = ChatMessage(
          id: complete.messageId,
          classId: arg,
          role: ChatRole.assistant,
          content: content,
          createdAt: now,
          updatedAt: now,
        );
        state = AsyncData([...state.valueOrNull ?? [], message]);
      }

      _refreshAfterCommand(complete.result);
    });

    _progressSub = ws.onProgress.where((e) => e.classId == arg).listen((
      progress,
    ) {
      final percent = progress.percent;
      if (progress.operationId.isNotEmpty) {
        ref.read(chatActiveOperationProvider(arg).notifier).state =
            progress.operationId;
      }
      _streaming.state = percent == null
          ? progress.message
          : '${progress.message} ($percent%)';
    });

    _errorSub = ws.onError.where((e) => e.classId == arg).listen((error) {
      _settle();
      _appendSystemMessage('Error: ${error.message}');
    });

    var wasConnected = ws.isConnectedTo(arg);
    _stateSub = ws.onStateChange.listen((_) {
      final connected = ws.isConnectedTo(arg);
      if (!connected) {
        // A reply cut off by a disconnect or Class switch would otherwise
        // stay on screen as a half-finished bubble. The command itself keeps
        // running on the backend; its result arrives with the history reload.
        _settle();
      } else if (!wasConnected) {
        // Replies that finished while the socket was down are in history.
        unawaited(_reloadHistory());
      }
      wasConnected = connected;
    });

    ref.onDispose(() {
      _chunkSub?.cancel();
      _completeSub?.cancel();
      _progressSub?.cancel();
      _errorSub?.cancel();
      _stateSub?.cancel();
    });

    return apiClient.getChatHistory(arg);
  }

  /// Sends [content] to this notifier's Class. Returns false, and shows a
  /// system message, when the chat isn't connected to that Class.
  bool sendMessage(String content) {
    final ws = ref.read(webSocketServiceProvider);
    if (!ws.isConnectedTo(arg)) {
      _appendSystemMessage(
        'Not connected to the backend, so the message was not sent. '
        'Try again in a moment.',
      );
      return false;
    }

    final now = DateTime.now();
    final userMessage = ChatMessage(
      id: 'local-${now.millisecondsSinceEpoch}',
      classId: arg,
      role: ChatRole.user,
      content: content,
      command: content.startsWith('/') ? content.split(' ').first : null,
      createdAt: now,
      updatedAt: now,
    );
    state = AsyncData([...state.valueOrNull ?? [], userMessage]);

    ws.sendMessage(arg, content);
    ref.read(chatAwaitingReplyProvider(arg).notifier).state = true;
    if (content.startsWith('/')) {
      ref.read(taskListProvider.notifier).startPolling();
    }
    return true;
  }

  /// Asks the backend to cancel the operation this chat is following.
  void stop() {
    final operationId = ref.read(chatActiveOperationProvider(arg));
    if (operationId == null) return;
    ref.read(webSocketServiceProvider).cancelOperation(operationId);
  }

  void _appendSystemMessage(String content) {
    final now = DateTime.now();
    final message = ChatMessage(
      id: 'system-${now.microsecondsSinceEpoch}',
      classId: arg,
      role: ChatRole.system,
      content: content,
      createdAt: now,
      updatedAt: now,
    );
    state = AsyncData([...state.valueOrNull ?? [], message]);
  }

  Future<void> _reloadHistory() async {
    try {
      final messages = await ref.read(apiClientProvider).getChatHistory(arg);
      state = AsyncData(messages);
    } catch (_) {
      // Keep what is on screen; the next reconnect tries again.
    }
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
      case '/flashcards':
      case '/quiz':
        final kind = command == '/flashcards' ? StudyKind.deck : StudyKind.quiz;
        ref.invalidate(
          kind == StudyKind.deck
              ? deckListProvider(arg)
              : quizListProvider(arg),
        );
        if (result['id'] case final String id) {
          ref.read(sidebarModeProvider.notifier).state = SidebarMode.study;
          ref.read(studySelectionProvider.notifier).state = StudySelection(
            kind,
            id,
          );
        }
    }
  }
}
