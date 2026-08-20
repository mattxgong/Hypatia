import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/chat_message.dart';

final chatMessagesProvider =
    NotifierProvider.family<ChatMessagesNotifier, List<ChatMessage>, String>(
      ChatMessagesNotifier.new,
    );

final chatInputProvider = StateProvider<String>((ref) => '');

class ChatMessagesNotifier extends FamilyNotifier<List<ChatMessage>, String> {
  @override
  List<ChatMessage> build(String arg) {
    return [];
  }

  void addMessage(ChatMessage message) {
    state = [...state, message];
  }

  void clear() {
    state = [];
  }
}
