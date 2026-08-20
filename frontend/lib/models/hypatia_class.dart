class HypatiaClass {
  const HypatiaClass({
    required this.id,
    required this.name,
    this.description = '',
    this.fileCount = 0,
    this.pageCount = 0,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String name;
  final String description;
  final int fileCount;
  final int pageCount;
  final DateTime createdAt;
  final DateTime updatedAt;

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
