enum CardType {
  basic('basic'),
  cloze('cloze');

  const CardType(this.value);
  final String value;

  static CardType fromString(String value) => CardType.values.firstWhere(
    (e) => e.value == value,
    orElse: () => CardType.basic,
  );
}

enum QuestionType {
  mcq('mcq', 'Multiple choice'),
  trueFalse('tf', 'True / false'),
  matching('matching', 'Matching'),
  fill('fill', 'Fill in the blank'),
  short('short', 'Short answer');

  const QuestionType(this.value, this.label);
  final String value;
  final String label;

  static QuestionType fromString(String value) => QuestionType.values
      .firstWhere((e) => e.value == value, orElse: () => QuestionType.mcq);
}

enum ReviewRating { again, hard, good, easy }

enum GenerationMethod {
  heuristic('heuristic', 'Offline'),
  llm('llm', 'AI'),
  hybrid('hybrid', 'Hybrid');

  const GenerationMethod(this.value, this.label);
  final String value;
  final String label;

  bool get usesAi => this != GenerationMethod.heuristic;
}

/// Offline generation returns the new item's [id]; AI generation runs as a
/// background task and returns its [taskId] instead.
class GenerationStart {
  const GenerationStart.done(String this.id) : taskId = null;
  const GenerationStart.running(String this.taskId) : id = null;

  final String? id;
  final String? taskId;
}

final _clozePattern = RegExp(r'\{\{c\d+::(.+?)(?:::[^}]*)?\}\}');

/// Cloze text with every deletion replaced by `[...]`.
String clozeQuestion(String front) => front.replaceAll(_clozePattern, '[...]');

/// Cloze text with every deletion revealed in bold.
String clozeAnswer(String front) =>
    front.replaceAllMapped(_clozePattern, (m) => '**${m[1]}**');

/// Whole scores without decimals, partial ones (matching credit) with one.
String formatScore(double value) => value == value.roundToDouble()
    ? value.toInt().toString()
    : value.toStringAsFixed(1);

class Deck {
  const Deck({
    required this.id,
    required this.classId,
    required this.name,
    this.description,
    required this.generationMethod,
    required this.cardCount,
    required this.dueCount,
    required this.staleCount,
    required this.createdAt,
  });

  factory Deck.fromJson(Map<String, dynamic> json) => Deck(
    id: json['id'] as String,
    classId: json['class_id'] as String,
    name: json['name'] as String,
    description: json['description'] as String?,
    generationMethod: json['generation_method'] as String,
    cardCount: json['card_count'] as int,
    dueCount: json['due_count'] as int,
    staleCount: json['stale_count'] as int,
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  final String id;
  final String classId;
  final String name;
  final String? description;
  final String generationMethod;
  final int cardCount;
  final int dueCount;
  final int staleCount;
  final DateTime createdAt;
}

class Flashcard {
  const Flashcard({
    required this.id,
    required this.deckId,
    required this.cardType,
    required this.front,
    required this.back,
    required this.origin,
    required this.pagePaths,
    required this.stale,
    required this.repetitions,
    required this.intervalDays,
  });

  factory Flashcard.fromJson(Map<String, dynamic> json) => Flashcard(
    id: json['id'] as String,
    deckId: json['deck_id'] as String,
    cardType: CardType.fromString(json['card_type'] as String),
    front: json['front'] as String,
    back: json['back'] as String,
    origin: json['origin'] as String,
    pagePaths: (json['page_paths'] as List<dynamic>).cast<String>(),
    stale: json['stale'] as bool,
    repetitions: json['repetitions'] as int,
    intervalDays: json['interval_days'] as int,
  );

  final String id;
  final String deckId;
  final CardType cardType;
  final String front;
  final String back;
  final String origin;
  final List<String> pagePaths;
  final bool stale;
  final int repetitions;
  final int intervalDays;

  String get question =>
      cardType == CardType.cloze ? clozeQuestion(front) : front;

  String get answer => cardType == CardType.cloze ? clozeAnswer(front) : back;
}

class QuizSummary {
  const QuizSummary({
    required this.id,
    required this.classId,
    required this.name,
    required this.questionCount,
    required this.staleCount,
    required this.attemptCount,
    this.lastScore,
    this.lastMaxScore,
    required this.createdAt,
  });

  factory QuizSummary.fromJson(Map<String, dynamic> json) => QuizSummary(
    id: json['id'] as String,
    classId: json['class_id'] as String,
    name: json['name'] as String,
    questionCount: json['question_count'] as int,
    staleCount: json['stale_count'] as int,
    attemptCount: json['attempt_count'] as int,
    lastScore: (json['last_score'] as num?)?.toDouble(),
    lastMaxScore: (json['last_max_score'] as num?)?.toDouble(),
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  final String id;
  final String classId;
  final String name;
  final int questionCount;
  final int staleCount;
  final int attemptCount;
  final double? lastScore;
  final double? lastMaxScore;
  final DateTime createdAt;
}

class QuizQuestion {
  const QuizQuestion({
    required this.id,
    required this.position,
    required this.type,
    required this.prompt,
    this.options = const [],
    this.left = const [],
    this.right = const [],
    required this.pagePaths,
    required this.stale,
  });

  factory QuizQuestion.fromJson(Map<String, dynamic> json) {
    final choices = json['choices'] as Map<String, dynamic>?;
    List<String> list(String key) =>
        (choices?[key] as List<dynamic>?)?.cast<String>() ?? const [];
    return QuizQuestion(
      id: json['id'] as String,
      position: json['position'] as int,
      type: QuestionType.fromString(json['question_type'] as String),
      prompt: json['prompt'] as String,
      options: list('options'),
      left: list('left'),
      right: list('right'),
      pagePaths: (json['page_paths'] as List<dynamic>).cast<String>(),
      stale: json['stale'] as bool,
    );
  }

  final String id;
  final int position;
  final QuestionType type;
  final String prompt;
  final List<String> options;
  final List<String> left;
  final List<String> right;
  final List<String> pagePaths;
  final bool stale;
}

class Quiz {
  const Quiz({required this.summary, required this.questions});

  factory Quiz.fromJson(Map<String, dynamic> json) => Quiz(
    summary: QuizSummary.fromJson(json),
    questions: (json['questions'] as List<dynamic>)
        .map((e) => QuizQuestion.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  final QuizSummary summary;
  final List<QuizQuestion> questions;
}

class QuestionResult {
  const QuestionResult({
    required this.questionId,
    required this.score,
    this.correct,
    required this.status,
    this.response,
    required this.expected,
    this.explanation,
    this.feedback,
    this.grader,
  });

  factory QuestionResult.fromJson(Map<String, dynamic> json) => QuestionResult(
    questionId: json['question_id'] as String,
    score: (json['score'] as num).toDouble(),
    correct: json['correct'] as bool?,
    status: json['status'] as String,
    response: json['response'] as Map<String, dynamic>?,
    expected: json['expected'] as Map<String, dynamic>,
    explanation: json['explanation'] as String?,
    feedback: json['feedback'] as String?,
    grader: json['grader'] as String?,
  );

  final String questionId;
  final double score;
  final bool? correct;
  final String status;
  final Map<String, dynamic>? response;
  final Map<String, dynamic> expected;
  final String? explanation;

  /// AI grader's comment on a short answer.
  final String? feedback;

  /// `ai` or `self` for short answers.
  final String? grader;

  bool get needsSelfReview => status == 'needs_self_review';
}

class QuizAttempt {
  const QuizAttempt({
    required this.id,
    required this.score,
    required this.maxScore,
    required this.results,
    required this.createdAt,
  });

  factory QuizAttempt.fromJson(Map<String, dynamic> json) => QuizAttempt(
    id: json['id'] as String,
    score: (json['score'] as num).toDouble(),
    maxScore: (json['max_score'] as num).toDouble(),
    results: (json['results'] as List<dynamic>)
        .map((e) => QuestionResult.fromJson(e as Map<String, dynamic>))
        .toList(),
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  final String id;
  final double score;
  final double maxScore;
  final List<QuestionResult> results;
  final DateTime createdAt;
}

/// Which wiki pages a generation request covers.
class StudyScope {
  const StudyScope.wholeClass()
    : type = 'class',
      query = null,
      paths = null,
      fileId = null;
  const StudyScope.topic(String this.query)
    : type = 'topic',
      paths = null,
      fileId = null;
  const StudyScope.pages(List<String> this.paths)
    : type = 'pages',
      query = null,
      fileId = null;
  const StudyScope.file(String this.fileId)
    : type = 'file',
      query = null,
      paths = null;

  final String type;
  final String? query;
  final List<String>? paths;
  final String? fileId;

  Map<String, dynamic> toJson() => {
    'type': type,
    'query': ?query,
    'paths': ?paths,
    'file_id': ?fileId,
  };
}
