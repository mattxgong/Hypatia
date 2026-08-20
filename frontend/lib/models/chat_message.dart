enum ChatRole { user, assistant, system }

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    this.command,
    required this.createdAt,
  });

  final String id;
  final ChatRole role;
  final String content;
  final String? command;
  final DateTime createdAt;
}
