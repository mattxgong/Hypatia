import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/study.dart';
import '../../providers/class_provider.dart';
import '../../providers/study_provider.dart';
import '../../services/api_client.dart';
import '../common/error_card.dart';
import '../common/wiki_markdown.dart';
import 'flashcard_review.dart' show studyMarkdownStyle;

/// Center-panel practice quiz: answer every question, submit, review results.
class QuizView extends ConsumerStatefulWidget {
  const QuizView({super.key, required this.quizId});

  final String quizId;

  @override
  ConsumerState<QuizView> createState() => _QuizViewState();
}

class _QuizViewState extends ConsumerState<QuizView> {
  final Map<String, Map<String, dynamic>> _answers = {};
  QuizAttempt? _attempt;
  bool _submitting = false;

  Future<void> _submit(String classId, Quiz quiz) async {
    setState(() => _submitting = true);
    try {
      final attempt = await ref
          .read(apiClientProvider)
          .submitQuizAttempt(classId, quiz.summary.id, _answers);
      if (!mounted) return;
      setState(() => _attempt = attempt);
      ref.invalidate(quizListProvider(classId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Submit failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _retake() => setState(() {
    _answers.clear();
    _attempt = null;
  });

  Future<void> _selfGrade(
    String classId,
    Quiz quiz,
    String questionId,
    bool correct,
  ) async {
    final attempt = _attempt;
    if (attempt == null) return;
    try {
      final updated = await ref.read(apiClientProvider).selfGradeAttempt(
        classId,
        quiz.summary.id,
        attempt.id,
        {questionId: correct},
      );
      if (!mounted) return;
      setState(() => _attempt = updated);
      ref.invalidate(quizListProvider(classId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Could not save: ${e.detail}')));
      }
    }
  }

  void _answer(String questionId, Map<String, dynamic> response) {
    if (_attempt != null) return;
    setState(() => _answers[questionId] = response);
  }

  @override
  Widget build(BuildContext context) {
    final classId = ref.watch(currentClassIdProvider);
    if (classId == null) return const SizedBox.shrink();
    final key = (classId: classId, quizId: widget.quizId);
    final quizAsync = ref.watch(quizProvider(key));

    return quizAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: ErrorCard(
          error: e,
          onRetry: () => ref.invalidate(quizProvider(key)),
        ),
      ),
      data: (quiz) => _buildQuiz(context, classId, quiz),
    );
  }

  Widget _buildQuiz(BuildContext context, String classId, Quiz quiz) {
    final theme = Theme.of(context);
    final attempt = _attempt;
    final results = {
      for (final r in attempt?.results ?? const <QuestionResult>[])
        r.questionId: r,
    };
    final answered = quiz.questions
        .where((q) => _answers.containsKey(q.id))
        .length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: theme.dividerColor)),
          ),
          child: Row(
            children: [
              const Icon(Icons.quiz_outlined, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(quiz.summary.name, style: theme.textTheme.titleMedium),
                    Text(
                      attempt == null
                          ? '$answered of ${quiz.questions.length} answered'
                          : 'Score: ${formatScore(attempt.score)} / '
                                '${formatScore(attempt.maxScore)}',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              if (attempt == null)
                FilledButton(
                  onPressed: _submitting || answered == 0
                      ? null
                      : () => _submit(classId, quiz),
                  child: _submitting
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Submit'),
                )
              else
                OutlinedButton.icon(
                  onPressed: _retake,
                  icon: const Icon(Icons.replay, size: 16),
                  label: const Text('Retake'),
                ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(24),
            itemCount: quiz.questions.length,
            itemBuilder: (context, index) {
              final question = quiz.questions[index];
              return Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 760),
                  child: _QuestionCard(
                    number: index + 1,
                    question: question,
                    response: _answers[question.id],
                    result: results[question.id],
                    onAnswer: (response) => _answer(question.id, response),
                    onSelfGrade: (correct) =>
                        _selfGrade(classId, quiz, question.id, correct),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _QuestionCard extends ConsumerWidget {
  const _QuestionCard({
    required this.number,
    required this.question,
    required this.response,
    required this.result,
    required this.onAnswer,
    required this.onSelfGrade,
  });

  final int number;
  final QuizQuestion question;
  final Map<String, dynamic>? response;
  final QuestionResult? result;
  final ValueChanged<Map<String, dynamic>> onAnswer;
  final ValueChanged<bool> onSelfGrade;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final style = studyMarkdownStyle(theme);
    final result = this.result;
    final graded = result != null;

    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text(
                  'Question $number · ${question.type.label}',
                  style: theme.textTheme.labelMedium,
                ),
                const Spacer(),
                if (question.stale)
                  Tooltip(
                    message: 'The wiki page behind this question has changed',
                    child: Icon(
                      Icons.update,
                      size: 16,
                      color: theme.colorScheme.tertiary,
                    ),
                  ),
                if (result != null) _ResultBadge(result: result),
              ],
            ),
            const SizedBox(height: 8),
            WikiMarkdown(
              data: question.prompt,
              styleSheet: style,
              scrollable: false,
            ),
            const SizedBox(height: 12),
            _AnswerInput(
              question: question,
              response: response,
              expected: result?.expected,
              enabled: !graded,
              onAnswer: onAnswer,
            ),
            if (result?.feedback case final feedback?) ...[
              const SizedBox(height: 8),
              Text('Feedback', style: theme.textTheme.labelMedium),
              const SizedBox(height: 2),
              Text(feedback),
            ],
            if (result != null && result.needsSelfReview) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  const Text('Compare with the model answer:'),
                  OutlinedButton.icon(
                    onPressed: () => onSelfGrade(true),
                    icon: const Icon(Icons.check, size: 16),
                    label: const Text('I got it right'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => onSelfGrade(false),
                    icon: const Icon(Icons.close, size: 16),
                    label: const Text('I got it wrong'),
                  ),
                ],
              ),
            ],
            if (result?.explanation case final explanation?) ...[
              const Divider(height: 24),
              Text('Explanation', style: theme.textTheme.labelMedium),
              const SizedBox(height: 4),
              WikiMarkdown(
                data: explanation,
                styleSheet: style,
                scrollable: false,
              ),
            ],
            if (graded && question.pagePaths.isNotEmpty)
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => openWikiPage(ref, question.pagePaths.first),
                  icon: const Icon(Icons.menu_book_outlined, size: 16),
                  label: const Text('Open source page'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ResultBadge extends StatelessWidget {
  const _ResultBadge({required this.result});

  final QuestionResult result;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (icon, color, label) = switch (result.status) {
      'unanswered' => (Icons.remove_circle_outline, scheme.outline, 'Skipped'),
      'needs_self_review' => (
        Icons.help_outline,
        scheme.tertiary,
        'Check yourself',
      ),
      _ when result.correct == true => (
        Icons.check_circle,
        Colors.green.shade600,
        'Correct',
      ),
      _ when result.score > 0 => (
        Icons.timelapse,
        scheme.tertiary,
        '${(result.score * 100).round()}%',
      ),
      _ => (Icons.cancel, scheme.error, 'Incorrect'),
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 4),
        Text(
          result.grader == 'ai' ? '$label (AI graded)' : label,
          style: TextStyle(color: color),
        ),
      ],
    );
  }
}

class _AnswerInput extends StatelessWidget {
  const _AnswerInput({
    required this.question,
    required this.response,
    required this.expected,
    required this.enabled,
    required this.onAnswer,
  });

  final QuizQuestion question;
  final Map<String, dynamic>? response;
  final Map<String, dynamic>? expected;
  final bool enabled;
  final ValueChanged<Map<String, dynamic>> onAnswer;

  @override
  Widget build(BuildContext context) {
    switch (question.type) {
      case QuestionType.mcq:
        return _ChoiceList(
          options: question.options,
          selected: response?['choice'] as int?,
          correct: expected?['choice'] as int?,
          enabled: enabled,
          onSelect: (i) => onAnswer({'choice': i}),
        );
      case QuestionType.trueFalse:
        final value = response?['value'] as bool?;
        final correct = expected?['value'] as bool?;
        return Wrap(
          spacing: 8,
          children: [
            for (final option in const [true, false])
              ChoiceChip(
                label: Text(option ? 'True' : 'False'),
                selected: value == option,
                avatar: correct == option
                    ? const Icon(Icons.check, size: 16)
                    : null,
                onSelected: enabled ? (_) => onAnswer({'value': option}) : null,
              ),
          ],
        );
      case QuestionType.matching:
        return _MatchingInput(
          question: question,
          pairs: (response?['pairs'] as List<dynamic>?)?.cast<int?>(),
          expected: (expected?['pairs'] as List<dynamic>?)?.cast<int>(),
          enabled: enabled,
          onChanged: (pairs) => onAnswer({'pairs': pairs}),
        );
      case QuestionType.fill:
        return _TextAnswer(
          initial: response?['text'] as String? ?? '',
          answer: (expected?['accepted'] as List<dynamic>?)
              ?.cast<String>()
              .join(' / '),
          enabled: enabled,
          onChanged: (text) => onAnswer({'text': text}),
        );
      case QuestionType.short:
        return _TextAnswer(
          initial: response?['text'] as String? ?? '',
          answer: expected?['reference'] as String?,
          answerLabel: 'Model answer',
          multiline: true,
          enabled: enabled,
          onChanged: (text) => onAnswer({'text': text}),
        );
    }
  }
}

class _ChoiceList extends StatelessWidget {
  const _ChoiceList({
    required this.options,
    required this.selected,
    required this.correct,
    required this.enabled,
    required this.onSelect,
  });

  final List<String> options;
  final int? selected;
  final int? correct;
  final bool enabled;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      children: [
        for (var i = 0; i < options.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Material(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: BorderSide(
                  color: correct == i
                      ? Colors.green.shade600
                      : selected == i
                      ? theme.colorScheme.primary
                      : theme.dividerColor,
                  width: correct == i || selected == i ? 2 : 1,
                ),
              ),
              child: InkWell(
                borderRadius: BorderRadius.circular(8),
                onTap: enabled ? () => onSelect(i) : null,
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        selected == i
                            ? Icons.radio_button_checked
                            : Icons.radio_button_unchecked,
                        size: 18,
                        semanticLabel: 'Option ${String.fromCharCode(65 + i)}',
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        // Selection gestures would otherwise swallow the tap.
                        child: IgnorePointer(
                          child: WikiMarkdown(
                            data: options[i],
                            styleSheet: studyMarkdownStyle(theme),
                            scrollable: false,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _MatchingInput extends StatelessWidget {
  const _MatchingInput({
    required this.question,
    required this.pairs,
    required this.expected,
    required this.enabled,
    required this.onChanged,
  });

  final QuizQuestion question;
  final List<int?>? pairs;
  final List<int>? expected;
  final bool enabled;
  final ValueChanged<List<int?>> onChanged;

  static String _letter(int index) => String.fromCharCode(65 + index);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final current = List<int?>.generate(
      question.left.length,
      (i) => pairs != null && i < pairs!.length ? pairs![i] : null,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var j = 0; j < question.right.length; j++)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${_letter(j)}.', style: theme.textTheme.titleSmall),
                const SizedBox(width: 8),
                Expanded(
                  child: WikiMarkdown(
                    data: question.right[j],
                    styleSheet: studyMarkdownStyle(theme),
                    scrollable: false,
                  ),
                ),
              ],
            ),
          ),
        const Divider(),
        for (var i = 0; i < question.left.length; i++)
          Row(
            children: [
              Expanded(child: Text(question.left[i])),
              DropdownButton<int>(
                hint: const Text('Pick'),
                value: current[i],
                onChanged: enabled
                    ? (v) => onChanged([...current]..[i] = v)
                    : null,
                items: [
                  for (var j = 0; j < question.right.length; j++)
                    DropdownMenuItem(value: j, child: Text(_letter(j))),
                ],
              ),
              if (expected != null && i < expected!.length) ...[
                const SizedBox(width: 8),
                Text(
                  current[i] == expected![i]
                      ? '\u2713'
                      : '\u2192 ${_letter(expected![i])}',
                  style: TextStyle(
                    color: current[i] == expected![i]
                        ? Colors.green.shade600
                        : theme.colorScheme.error,
                  ),
                ),
              ],
            ],
          ),
      ],
    );
  }
}

class _TextAnswer extends StatefulWidget {
  const _TextAnswer({
    required this.initial,
    required this.answer,
    required this.enabled,
    required this.onChanged,
    this.answerLabel = 'Answer',
    this.multiline = false,
  });

  final String initial;

  /// Shown once graded.
  final String? answer;
  final String answerLabel;
  final bool multiline;
  final bool enabled;
  final ValueChanged<String> onChanged;

  @override
  State<_TextAnswer> createState() => _TextAnswerState();
}

class _TextAnswerState extends State<_TextAnswer> {
  late final _controller = TextEditingController(text: widget.initial);

  @override
  void didUpdateWidget(_TextAnswer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initial.isEmpty && _controller.text.isNotEmpty) {
      _controller.clear();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final answer = widget.answer;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: _controller,
          enabled: widget.enabled,
          minLines: widget.multiline ? 2 : 1,
          maxLines: widget.multiline ? 6 : 1,
          decoration: const InputDecoration(labelText: 'Your answer'),
          onChanged: widget.onChanged,
        ),
        if (answer != null && answer.isNotEmpty) ...[
          const SizedBox(height: 6),
          WikiMarkdown(
            data: '**${widget.answerLabel}:** $answer',
            styleSheet: studyMarkdownStyle(Theme.of(context)),
            scrollable: false,
          ),
        ],
      ],
    );
  }
}
