enum WikiCategory {
  sourceSummary('source-summary'),
  concept('concept'),
  entity('entity'),
  wikiIndex('index'),
  wikiLog('log'),
  schema('schema');

  const WikiCategory(this.value);
  final String value;
}

class WikiPageSummary {
  const WikiPageSummary({
    required this.path,
    required this.title,
    required this.category,
  });

  final String path;
  final String title;
  final WikiCategory category;
}

class WikiPage {
  const WikiPage({
    required this.path,
    required this.title,
    required this.category,
    required this.content,
    this.updatedAt,
    this.isUserEdited = false,
  });

  final String path;
  final String title;
  final WikiCategory category;
  final String content;
  final DateTime? updatedAt;
  final bool isUserEdited;
}
