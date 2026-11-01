import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/chat_message.dart';
import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/models/source_file.dart';
import 'package:frontend/models/study.dart';
import 'package:frontend/models/task_status.dart';
import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/providers/chat_provider.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/settings_provider.dart';
import 'package:frontend/providers/study_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/sidebar/sidebar.dart';
import 'package:frontend/widgets/study/flashcard_review.dart';
import 'package:frontend/widgets/study/generate_study_dialog.dart';
import 'package:frontend/widgets/study/quiz_view.dart';
import 'package:frontend/widgets/study/session_summary.dart';

const _classId = 'class-1';

Flashcard _card(String id, String front, String back, {CardType? type}) =>
    Flashcard.fromJson({
      'id': id,
      'deck_id': 'deck-1',
      'card_type': (type ?? CardType.basic).value,
      'front': front,
      'back': back,
      'origin': 'heuristic',
      'page_paths': ['pages/concept/x.md'],
      'stale': false,
      'repetitions': 0,
      'interval_days': 0,
    });

Deck _deck({int due = 2, String? nextDue}) => Deck.fromJson({
  'id': 'deck-1',
  'class_id': _classId,
  'name': 'NLP flashcards',
  'description': null,
  'generation_method': 'heuristic',
  'card_count': 2,
  'due_count': due,
  'stale_count': 1,
  'next_due_at': nextDue,
  'created_at': '2026-10-01T00:00:00',
});

QuizSummary _quizSummary() => QuizSummary.fromJson({
  'id': 'quiz-1',
  'class_id': _classId,
  'name': 'NLP quiz',
  'question_count': 1,
  'stale_count': 0,
  'attempt_count': 0,
  'last_score': null,
  'last_max_score': null,
  'created_at': '2026-10-01T00:00:00',
});

Quiz _quiz({bool twoQuestions = false, int points = 1}) => Quiz.fromJson({
  'id': 'quiz-1',
  'class_id': _classId,
  'name': 'NLP quiz',
  'question_count': 1,
  'stale_count': 0,
  'attempt_count': 0,
  'last_score': null,
  'last_max_score': null,
  'created_at': '2026-10-01T00:00:00',
  'questions': [
    {
      'id': 'q1',
      'position': 0,
      'question_type': 'mcq',
      'prompt': 'What is Zipf law?',
      'choices': {
        'options': ['A power law', 'A tokenizer'],
      },
      'points': points,
      'page_paths': <String>[],
      'stale': false,
    },
    if (twoQuestions)
      {
        'id': 'q2',
        'position': 1,
        'question_type': 'short',
        'prompt': 'What does Viterbi find?',
        'choices': null,
        'page_paths': <String>[],
        'stale': false,
      },
  ],
});

/// Records what the quiz view sends to chat instead of opening a socket.
class _RecordingChat extends ChatMessagesNotifier {
  final sent = <String>[];

  @override
  Future<List<ChatMessage>> build(String arg) async => const [];

  @override
  bool sendMessage(String content) {
    sent.add(content);
    return true;
  }
}

class _FakeApi extends ApiClient {
  _FakeApi() : super(baseUrl: 'http://test');

  final reviews = <(String, ReviewRating)>[];
  final submitted = <Map<String, Map<String, dynamic>>>[];
  final generatedScopes = <Map<String, dynamic>>[];
  final generatedMethods = <GenerationMethod>[];
  List<Flashcard> due = [
    _card('c1', 'What is entropy?', 'Uncertainty.'),
    _card(
      'c2',
      'The {{c1::Viterbi}} algorithm decodes.',
      'Viterbi',
      type: CardType.cloze,
    ),
  ];

  @override
  Future<List<Flashcard>> listDueCards(
    String classId,
    String deckId, {
    int limit = 20,
  }) async => due;

  final deletedCards = <String>[];

  @override
  Future<List<Flashcard>> listCards(String classId, String deckId) async =>
      due.where((c) => !deletedCards.contains(c.id)).toList();

  @override
  Future<void> deleteCard(String classId, String deckId, String cardId) async {
    deletedCards.add(cardId);
  }

  @override
  Future<Flashcard> reviewCard(
    String classId,
    String deckId,
    String cardId,
    ReviewRating rating,
  ) async {
    reviews.add((cardId, rating));
    return due.firstWhere((c) => c.id == cardId);
  }

  /// What the next submitted attempt scores on q1.
  double resultScore = 1;
  int resultPoints = 1;

  @override
  Future<QuizAttempt> submitQuizAttempt(
    String classId,
    String quizId,
    Map<String, Map<String, dynamic>> answers,
  ) async {
    submitted.add(answers);
    return QuizAttempt.fromJson({
      'id': 'a1',
      'score': resultScore * resultPoints,
      'max_score': resultPoints,
      'created_at': '2026-10-01T00:00:00',
      'results': [
        {
          'question_id': 'q1',
          'score': resultScore,
          'points': resultPoints,
          'correct': resultScore == 1,
          'status': 'graded',
          'response': {'choice': 0},
          'expected': {'choice': 0},
          'explanation': 'Rank and frequency follow a power law.',
        },
      ],
    });
  }

  @override
  Future<GenerationStart> generateDeck(
    String classId, {
    required StudyScope scope,
    required int count,
    required List<CardType> cardTypes,
    GenerationMethod method = GenerationMethod.heuristic,
    String? name,
  }) async {
    generatedScopes.add(scope.toJson());
    generatedMethods.add(method);
    return method.usesAi
        ? const GenerationStart.running('task-1')
        : const GenerationStart.done('deck-1');
  }

  String taskStatus = 'running';

  @override
  Future<TaskStatus> getTask(String taskId) async => TaskStatus(
    taskId: taskId,
    operation: 'Generate flashcards',
    classId: _classId,
    status: taskStatus,
    progress: 40,
    message: 'Writing flashcards: part 2 of 3',
    error: taskStatus == 'failed' ? 'LLM error: quota' : null,
    createdAt: '2026-10-01T00:00:00',
  );

  final undos = <String>[];

  @override
  Future<Flashcard> undoReview(
    String classId,
    String deckId,
    String cardId,
  ) async {
    undos.add(cardId);
    return due.firstWhere((c) => c.id == cardId);
  }

  final selfGrades = <Map<String, bool>>[];

  @override
  Future<QuizAttempt> selfGradeAttempt(
    String classId,
    String quizId,
    String attemptId,
    Map<String, bool> grades,
  ) async {
    selfGrades.add(grades);
    return _shortAttempt(selfGraded: true);
  }
}

QuizAttempt _shortAttempt({bool selfGraded = false}) => QuizAttempt.fromJson({
  'id': 'a2',
  'score': selfGraded ? 1 : 0,
  'max_score': 1,
  'created_at': '2026-10-01T00:00:00',
  'results': [
    {
      'question_id': 'q1',
      'score': selfGraded ? 1 : 0,
      'correct': selfGraded ? true : null,
      'status': selfGraded ? 'graded' : 'needs_self_review',
      'grader': selfGraded ? 'self' : null,
      'response': {'text': 'the best path'},
      'expected': {'reference': 'The most probable state sequence.'},
      'explanation': null,
    },
  ],
});

class _MockClassListNotifier extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [
    HypatiaClass(
      id: _classId,
      name: 'NLP',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    ),
  ];
}

void main() {
  late SharedPreferences prefs;
  late _FakeApi api;
  late Deck deck;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    api = _FakeApi();
    deck = _deck();
  });

  Widget wrap(
    Widget child, {
    List<Override> overrides = const [],
    bool aiConnected = false,
    bool nestedApp = false,
  }) {
    return ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        apiClientProvider.overrideWithValue(api),
        llmConnectionStatusProvider.overrideWith(
          (ref) async => LlmConnectionStatus(
            provider: 'copilot',
            model: null,
            connected: aiConnected,
          ),
        ),
        classListProvider.overrideWith(() => _MockClassListNotifier()),
        currentClassIdProvider.overrideWith((ref) => _classId),
        wikiTreeProvider(
          _classId,
        ).overrideWith((ref) async => const <WikiPageSummary>[]),
        fileListProvider(
          _classId,
        ).overrideWith((ref) async => const <SourceFile>[]),
        deckListProvider(_classId).overrideWith((ref) async => [deck]),
        quizListProvider(
          _classId,
        ).overrideWith((ref) async => [_quizSummary()]),
        ...overrides,
      ],
      // The real app nests its routed MaterialApp inside a startup MaterialApp.
      child: nestedApp
          ? MaterialApp(
              home: MaterialApp(home: Scaffold(body: child)),
            )
          : MaterialApp(home: Scaffold(body: child)),
    );
  }

  void largeSurface(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  group('models', () {
    test('cloze cards hide and reveal the deletion', () {
      final card = _card(
        'c',
        'The {{c1::Viterbi}} algorithm.',
        'Viterbi',
        type: CardType.cloze,
      );
      expect(card.question, 'The [...] algorithm.');
      expect(card.answer, 'The **Viterbi** algorithm.');
    });

    test('scope json omits unused fields', () {
      expect(const StudyScope.wholeClass().toJson(), {'type': 'class'});
      expect(const StudyScope.topic('hmm').toJson(), {
        'type': 'topic',
        'query': 'hmm',
      });
    });

    test('formatScore', () {
      expect(formatScore(3), '3');
      expect(formatScore(2.5), '2.5');
    });
  });

  testWidgets('sidebar Study tab lists decks and quizzes', (tester) async {
    largeSurface(tester);
    await tester.pumpWidget(wrap(const SizedBox(width: 300, child: Sidebar())));
    await tester.pumpAndSettle();

    expect(find.textContaining('Concepts'), findsOneWidget);
    await tester.tap(find.text('Study'));
    await tester.pumpAndSettle();

    expect(find.text('NLP flashcards'), findsOneWidget);
    expect(find.text('2 due · 2 cards'), findsOneWidget);
    expect(find.text('NLP quiz'), findsOneWidget);
    expect(find.textContaining('not taken'), findsOneWidget);
    expect(find.byIcon(Icons.update), findsOneWidget);
  });

  testWidgets('a deleted card can be brought back with Undo', (tester) async {
    largeSurface(tester);
    await tester.pumpWidget(wrap(const FlashcardReview(deckId: 'deck-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Browse cards').first);
    await tester.pumpAndSettle();
    expect(find.text('What is entropy?'), findsOneWidget);

    await tester.tap(find.byTooltip('Delete card').first);
    await tester.pumpAndSettle();
    expect(find.text('What is entropy?'), findsNothing);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(find.text('What is entropy?'), findsOneWidget);
    expect(api.deletedCards, isEmpty);

    // Without Undo, the card is deleted once the notice goes away.
    await tester.tap(find.byTooltip('Delete card').first);
    await tester
        .pumpAndSettle(); // the notice's countdown starts once it's shown
    await tester.pump(const Duration(seconds: 6));
    await tester.pumpAndSettle();
    expect(api.deletedCards, ['c1']);
    expect(find.text('What is entropy?'), findsNothing);
  });

  testWidgets('review flips a card and records ratings', (tester) async {
    largeSurface(tester);
    await tester.pumpWidget(wrap(const FlashcardReview(deckId: 'deck-1')));
    await tester.pumpAndSettle();

    expect(find.text('What is entropy?'), findsOneWidget);
    expect(find.text('Uncertainty.'), findsNothing);

    await tester.tap(find.text('Show answer (Space)'));
    await tester.pumpAndSettle();
    expect(find.text('Uncertainty.'), findsOneWidget);

    await tester.tap(find.text('Good (3)'));
    await tester.pumpAndSettle();
    expect(api.reviews, [('c1', ReviewRating.good)]);
    expect(find.text('The [...] algorithm decodes.'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.digit4);
    await tester.pumpAndSettle();
    expect(api.reviews.last, ('c2', ReviewRating.easy));
    expect(find.text('Reviewed 2 cards'), findsOneWidget);
    expect(find.text('Good: 1'), findsOneWidget);
    expect(find.text('Easy: 1'), findsOneWidget);
    expect(find.text('No misses this time.'), findsOneWidget);
    expect(find.text('2 more cards are due now.'), findsOneWidget);
    expect(find.text('Keep studying'), findsOneWidget);
  });

  testWidgets('a session of misses points at the pages to revisit', (
    tester,
  ) async {
    largeSurface(tester);
    final soon = DateTime.now().add(const Duration(minutes: 10, seconds: 30));
    deck = _deck(due: 0, nextDue: soon.toUtc().toIso8601String());
    api.due = [_card('c1', 'What is entropy?', 'Uncertainty.')];
    await tester.pumpWidget(wrap(const FlashcardReview(deckId: 'deck-1')));
    await tester.pumpAndSettle();

    // Again sends the card to the back of this session; Easy then finishes it.
    for (final rating in [
      LogicalKeyboardKey.digit1,
      LogicalKeyboardKey.digit4,
    ]) {
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(rating);
      await tester.pumpAndSettle();
    }

    expect(find.text('Reviewed 2 cards'), findsOneWidget);
    expect(find.text('Again: 1'), findsOneWidget);
    expect(find.text('Worth another look:'), findsOneWidget);
    expect(find.text('x.md (1 miss)'), findsOneWidget);
    expect(find.text('Next review in 10 minutes.'), findsOneWidget);
    expect(find.text('Keep studying'), findsNothing);
  });

  testWidgets('summaries skip the pop-in when animations are off', (
    tester,
  ) async {
    await tester.pumpWidget(
      wrap(
        const MediaQuery(
          data: MediaQueryData(disableAnimations: true),
          child: SessionSummary(score: 0, maxScore: 2),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(TweenAnimationBuilder<double>), findsNothing);
    expect(find.text('You earned 0 of 2 points'), findsOneWidget);
    expect(find.text('No wiki pages to revisit.'), findsOneWidget);
  });

  testWidgets('quiz answers are submitted and graded', (tester) async {
    largeSurface(tester);
    await tester.pumpWidget(
      wrap(
        const QuizView(quizId: 'quiz-1'),
        overrides: [
          quizProvider((
            classId: _classId,
            quizId: 'quiz-1',
          )).overrideWith((ref) async => _quiz()),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('0 of 1 answered'), findsOneWidget);
    await tester.tap(
      find.ancestor(
        of: find.text('A power law'),
        matching: find.byType(InkWell),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('1 of 1 answered'), findsOneWidget);

    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();
    expect(api.submitted.single, {
      'q1': {'choice': 0},
    });
    expect(find.text('Score: 1 / 1'), findsOneWidget);
    expect(find.text('Correct · 1 / 1'), findsOneWidget);
    expect(find.text('Review my mistakes'), findsNothing);
    expect(find.text('You earned 1 of 1 point'), findsOneWidget);
    expect(find.text('No misses this time.'), findsOneWidget);
    expect(find.text('Rank and frequency follow a power law.'), findsOneWidget);
    expect(find.text('Retake'), findsOneWidget);
  });

  testWidgets('weighted questions show points and partial credit', (
    tester,
  ) async {
    largeSurface(tester);
    api
      ..resultScore = 0.5
      ..resultPoints = 3;
    final chat = _RecordingChat();
    late ProviderContainer container;
    await tester.pumpWidget(
      wrap(
        Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return const QuizView(quizId: 'quiz-1');
          },
        ),
        overrides: [
          quizProvider((
            classId: _classId,
            quizId: 'quiz-1',
          )).overrideWith((ref) async => _quiz(points: 3)),
          chatMessagesProvider.overrideWith(() => chat),
        ],
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text('Question 1 · Multiple choice · 3 points'),
      findsOneWidget,
    );

    await tester.tap(
      find.ancestor(
        of: find.text('A power law'),
        matching: find.byType(InkWell),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();

    expect(find.text('Score: 1.5 / 3'), findsOneWidget);
    expect(find.text('50% · 1.5 / 3'), findsOneWidget);
    // The question cites no wiki page, so there is nothing to point at.
    expect(find.text('No wiki pages to revisit.'), findsOneWidget);

    await tester.tap(find.text('Review my mistakes'));
    await tester.pumpAndSettle();
    expect(chat.sent, ['/review-quiz a1']);
    expect(container.read(chatRevealRequestProvider), 1);
  });

  Future<void> pumpTwoQuestionQuiz(WidgetTester tester) async {
    largeSurface(tester);
    await tester.pumpWidget(
      wrap(
        const QuizView(quizId: 'quiz-1'),
        overrides: [
          quizProvider((
            classId: _classId,
            quizId: 'quiz-1',
          )).overrideWith((ref) async => _quiz(twoQuestions: true)),
        ],
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('quiz keys move between questions and pick choices', (
    tester,
  ) async {
    await pumpTwoQuestionQuiz(tester);

    await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
    await tester.pumpAndSettle();
    expect(find.text('1 of 2 answered'), findsOneWidget);

    // On the short answer, number keys pick nothing; back on question 1 they do.
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit1);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit1);
    // A modifier means a shortcut, not an answer.
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Submit anyway'));
    await tester.pumpAndSettle();
    expect(api.submitted.single['q1'], {'choice': 0});
  });

  testWidgets('quiz keys type into a focused answer field', (tester) async {
    await pumpTwoQuestionQuiz(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit1);
    await tester.pumpAndSettle();

    await tester.tap(find.byType(TextField));
    await tester.enterText(find.byType(TextField), 'It finds the best path');
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();
    expect(api.submitted.single, {
      'q1': {'choice': 0},
      'q2': {'text': 'It finds the best path'},
    });
  });

  testWidgets('a rating can be undone from its notice', (tester) async {
    largeSurface(tester);
    await tester.pumpWidget(wrap(const FlashcardReview(deckId: 'deck-1')));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Show answer (Space)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Good (3)'));
    await tester.pumpAndSettle();
    expect(find.text('The [...] algorithm decodes.'), findsOneWidget);

    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(api.reviews, [('c1', ReviewRating.good)]);
    expect(api.undos, ['c1']);
    expect(find.text('What is entropy?'), findsOneWidget);
  });

  Widget quizWrap({ValueNotifier<bool>? shown, bool twoQuestions = false}) =>
      wrap(
        shown == null
            ? const QuizView(quizId: 'quiz-1')
            : ValueListenableBuilder<bool>(
                valueListenable: shown,
                builder: (context, show, _) => show
                    ? const QuizView(quizId: 'quiz-1')
                    : const Text('elsewhere'),
              ),
        overrides: [
          quizProvider((
            classId: _classId,
            quizId: 'quiz-1',
          )).overrideWith((ref) async => _quiz(twoQuestions: twoQuestions)),
        ],
      );

  testWidgets('submitting with unanswered questions asks first', (
    tester,
  ) async {
    largeSurface(tester);
    await tester.pumpWidget(quizWrap(twoQuestions: true));
    await tester.pumpAndSettle();
    await tester.tap(
      find.ancestor(
        of: find.text('A power law'),
        matching: find.byType(InkWell),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();
    expect(find.text('1 question is unanswered'), findsOneWidget);
    await tester.tap(find.text('Keep answering'));
    await tester.pumpAndSettle();
    expect(api.submitted, isEmpty);

    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Submit anyway'));
    await tester.pumpAndSettle();
    expect(api.submitted.single, {
      'q1': {'choice': 0},
    });
  });

  testWidgets('quiz answers survive leaving the quiz', (tester) async {
    largeSurface(tester);
    final shown = ValueNotifier(true);
    addTearDown(shown.dispose);
    await tester.pumpWidget(quizWrap(shown: shown));
    await tester.pumpAndSettle();

    await tester.tap(
      find.ancestor(
        of: find.text('A power law'),
        matching: find.byType(InkWell),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('1 of 1 answered'), findsOneWidget);

    shown.value = false;
    await tester.pumpAndSettle();
    expect(find.text('elsewhere'), findsOneWidget);
    shown.value = true;
    await tester.pumpAndSettle();
    expect(find.text('1 of 1 answered'), findsOneWidget);
  });

  testWidgets('generate dialog creates a deck and opens it', (tester) async {
    largeSurface(tester);
    late WidgetRef capturedRef;
    await tester.pumpWidget(
      wrap(
        Consumer(
          builder: (context, ref, _) {
            capturedRef = ref;
            return TextButton(
              onPressed: () => showGenerateStudyDialog(context),
              child: const Text('open'),
            );
          },
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(
      find.text('Built offline from your wiki pages (no AI).'),
      findsOneWidget,
    );
    await tester.tap(find.text('Generate'));
    await tester.pumpAndSettle();

    expect(api.generatedScopes, [
      {'type': 'class'},
    ]);
    expect(api.generatedMethods, [GenerationMethod.heuristic]);
    expect(find.text('Create study material'), findsNothing);
    expect(
      capturedRef.read(studySelectionProvider),
      const StudySelection(StudyKind.deck, 'deck-1'),
    );
    expect(capturedRef.read(sidebarModeProvider), SidebarMode.study);
  });

  testWidgets('with AI reachable the dialog defaults to AI and tracks a job', (
    tester,
  ) async {
    largeSurface(tester);
    late WidgetRef capturedRef;
    await tester.pumpWidget(
      wrap(
        Consumer(
          builder: (context, ref, _) {
            capturedRef = ref;
            return TextButton(
              onPressed: () => showGenerateStudyDialog(context),
              child: const Text('open'),
            );
          },
        ),
        aiConnected: true,
        nestedApp: true,
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Written by your AI model'), findsOneWidget);
    await tester.tap(find.text('Generate'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Create study material'), findsNothing);
    expect(api.generatedMethods, [GenerationMethod.llm]);
    final job = capturedRef.read(studyJobsProvider).single;
    expect(
      (job.taskId, job.kind, job.label),
      ('task-1', StudyKind.deck, 'All pages flashcards'),
    );
    expect(capturedRef.read(studySelectionProvider), isNull);
    expect(find.textContaining('Writing with AI'), findsOneWidget);
  });

  testWidgets('quiz dialog offers short answers and AI grading only with AI', (
    tester,
  ) async {
    largeSurface(tester);
    await tester.pumpWidget(
      wrap(
        Builder(
          builder: (context) => TextButton(
            onPressed: () =>
                showGenerateStudyDialog(context, kind: StudyMaterialKind.quiz),
            child: const Text('open'),
          ),
        ),
        aiConnected: true,
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Short answer'), findsOneWidget);
    expect(find.text('Grade short answers with AI'), findsOneWidget);

    await tester.tap(find.text('Offline'));
    await tester.pumpAndSettle();
    expect(find.text('Short answer'), findsNothing);
    expect(find.text('Grade short answers with AI'), findsNothing);
  });

  test('job polling drops finished jobs and keeps failures', () async {
    final container = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);
    final jobs = container.read(studyJobsProvider.notifier);
    jobs.track(
      const StudyJob(
        taskId: 'task-1',
        classId: _classId,
        kind: StudyKind.deck,
        label: 'Deck',
      ),
    );

    await jobs.poll();
    expect(container.read(studyJobsProvider).single.progress, 40);

    api.taskStatus = 'failed';
    await jobs.poll();
    expect(container.read(studyJobsProvider).single.error, 'LLM error: quota');

    jobs.dismiss('task-1');
    jobs.track(
      const StudyJob(
        taskId: 'task-2',
        classId: _classId,
        kind: StudyKind.quiz,
        label: 'Quiz',
      ),
    );
    api.taskStatus = 'complete';
    await jobs.poll();
    expect(container.read(studyJobsProvider), isEmpty);
  });

  testWidgets('short answers can be self-graded', (tester) async {
    largeSurface(tester);
    final quiz = Quiz.fromJson({
      'id': 'quiz-1',
      'class_id': _classId,
      'name': 'Short quiz',
      'question_count': 1,
      'stale_count': 0,
      'attempt_count': 0,
      'last_score': null,
      'last_max_score': null,
      'created_at': '2026-10-01T00:00:00',
      'questions': [
        {
          'id': 'q1',
          'position': 0,
          'question_type': 'short',
          'prompt': 'What does Viterbi find?',
          'choices': null,
          'page_paths': <String>[],
          'stale': false,
        },
      ],
    });
    final shortApi = _ShortAnswerApi();
    api = shortApi;
    await tester.pumpWidget(
      wrap(
        const QuizView(quizId: 'quiz-1'),
        overrides: [
          quizProvider((
            classId: _classId,
            quizId: 'quiz-1',
          )).overrideWith((ref) async => quiz),
        ],
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'the best path');
    await tester.pump();
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();
    expect(find.text('Check yourself'), findsOneWidget);
    expect(
      find.textContaining('The most probable state sequence.'),
      findsOneWidget,
    );

    await tester.tap(find.text('I got it right'));
    await tester.pumpAndSettle();
    expect(shortApi.selfGrades.single, {'q1': true});
    expect(find.text('Score: 1 / 1'), findsOneWidget);
    expect(find.text('I got it right'), findsNothing);
  });
}

class _ShortAnswerApi extends _FakeApi {
  @override
  Future<QuizAttempt> submitQuizAttempt(
    String classId,
    String quizId,
    Map<String, Map<String, dynamic>> answers,
  ) async {
    submitted.add(answers);
    return _shortAttempt();
  }
}
