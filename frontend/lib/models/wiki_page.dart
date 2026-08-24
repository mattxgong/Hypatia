enum WikiCategory {
  sourceSummary('source-summary'),
  concept('concept'),
  entity('entity'),
  synthesis('synthesis'),
  wikiIndex('index'),
  wikiLog('log'),
  schema('schema');

  const WikiCategory(this.value);
  final String value;

  static WikiCategory fromString(String value) {
    return WikiCategory.values.firstWhere(
      (e) => e.value == value,
      orElse: () => WikiCategory.concept,
    );
  }
}

class WikiPageSummary {
  const WikiPageSummary({
    required this.id,
    required this.path,
    required this.title,
    required this.category,
    this.updatedAt,
  });

  factory WikiPageSummary.fromJson(Map<String, dynamic> json) {
    return WikiPageSummary(
      id: json['id'] as String,
      path: json['path'] as String,
      title: json['title'] as String,
      category: WikiCategory.fromString(json['category'] as String),
      updatedAt: json['updated_at'] != null
          ? DateTime.parse(json['updated_at'] as String)
          : null,
    );
  }

  final String id;
  final String path;
  final String title;
  final WikiCategory category;
  final DateTime? updatedAt;

  Map<String, dynamic> toJson() => {
    'id': id,
    'path': path,
    'title': title,
    'category': category.value,
    'updated_at': updatedAt?.toIso8601String(),
  };
}

class WikiPage {
  const WikiPage({
    required this.id,
    required this.classId,
    required this.path,
    required this.title,
    required this.category,
    required this.content,
    this.sourceFileIds,
    required this.createdAt,
    required this.updatedAt,
  });

  factory WikiPage.fromJson(Map<String, dynamic> json) {
    return WikiPage(
      id: json['id'] as String,
      classId: json['class_id'] as String,
      path: json['path'] as String,
      title: json['title'] as String,
      category: WikiCategory.fromString(json['category'] as String),
      content: json['content'] as String,
      sourceFileIds: (json['source_file_ids'] as List<dynamic>?)
          ?.map((e) => e as String)
          .toList(),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String id;
  final String classId;
  final String path;
  final String title;
  final WikiCategory category;
  final String content;
  final List<String>? sourceFileIds;
  final DateTime createdAt;
  final DateTime updatedAt;

  Map<String, dynamic> toJson() => {
    'id': id,
    'class_id': classId,
    'path': path,
    'title': title,
    'category': category.value,
    'content': content,
    'source_file_ids': sourceFileIds,
    'created_at': createdAt.toIso8601String(),
    'updated_at': updatedAt.toIso8601String(),
  };
}

class WikiSearchResult {
  const WikiSearchResult({
    required this.pageId,
    required this.path,
    required this.title,
    required this.snippet,
    required this.rank,
  });

  factory WikiSearchResult.fromJson(Map<String, dynamic> json) {
    return WikiSearchResult(
      pageId: json['page_id'] as String,
      path: json['path'] as String,
      title: json['title'] as String,
      snippet: json['snippet'] as String,
      rank: (json['rank'] as num).toDouble(),
    );
  }

  final String pageId;
  final String path;
  final String title;
  final String snippet;
  final double rank;
}
