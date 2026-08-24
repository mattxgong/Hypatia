enum ChatRole {
  user('user'),
  assistant('assistant'),
  system('system');

  const ChatRole(this.value);
  final String value;

  static ChatRole fromString(String value) {
    return ChatRole.values.firstWhere(
      (e) => e.value == value,
      orElse: () => ChatRole.system,
    );
  }
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.classId,
    required this.role,
    required this.content,
    this.command,
    this.metadataJson,
    required this.createdAt,
    required this.updatedAt,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: json['id'] as String,
      classId: json['class_id'] as String,
      role: ChatRole.fromString(json['role'] as String),
      content: json['content'] as String,
      command: json['command'] as String?,
      metadataJson: json['metadata_json'] as Map<String, dynamic>?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String id;
  final String classId;
  final ChatRole role;
  final String content;
  final String? command;
  final Map<String, dynamic>? metadataJson;
  final DateTime createdAt;
  final DateTime updatedAt;

  Map<String, dynamic> toJson() => {
    'id': id,
    'class_id': classId,
    'role': role.value,
    'content': content,
    'command': command,
    'metadata_json': metadataJson,
    'created_at': createdAt.toIso8601String(),
    'updated_at': updatedAt.toIso8601String(),
  };
}
