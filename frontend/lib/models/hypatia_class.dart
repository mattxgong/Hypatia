class HypatiaClass {
  const HypatiaClass({
    required this.id,
    required this.name,
    this.description,
    this.fileCount = 0,
    this.pageCount = 0,
    required this.createdAt,
    required this.updatedAt,
  });

  factory HypatiaClass.fromJson(Map<String, dynamic> json) {
    return HypatiaClass(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      fileCount: (json['file_count'] as int?) ?? 0,
      pageCount: (json['page_count'] as int?) ?? 0,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String id;
  final String name;
  final String? description;
  final int fileCount;
  final int pageCount;
  final DateTime createdAt;
  final DateTime updatedAt;

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'description': description,
    'file_count': fileCount,
    'page_count': pageCount,
    'created_at': createdAt.toIso8601String(),
    'updated_at': updatedAt.toIso8601String(),
  };

  HypatiaClass copyWith({
    String? id,
    String? name,
    String? description,
    int? fileCount,
    int? pageCount,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return HypatiaClass(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      fileCount: fileCount ?? this.fileCount,
      pageCount: pageCount ?? this.pageCount,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}
