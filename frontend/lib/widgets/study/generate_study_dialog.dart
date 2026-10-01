import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/source_file.dart';
import '../../models/study.dart';
import '../../models/wiki_page.dart';
import '../../providers/class_provider.dart';
import '../../providers/file_provider.dart';
import '../../providers/settings_provider.dart';
import '../../providers/study_provider.dart';
import '../../providers/wiki_provider.dart';
import '../../services/api_client.dart';
import '../common/error_card.dart';

enum StudyMaterialKind { flashcards, quiz }

enum _ScopeType { wholeClass, topic, currentPage, file }

const _cardCounts = [10, 20, 30, 50, 100];
const _questionCounts = [5, 10, 15, 20, 30];
const _heuristicQuestionTypes = [
  QuestionType.mcq,
  QuestionType.trueFalse,
  QuestionType.matching,
  QuestionType.fill,
];
const _aiQuestionTypes = [..._heuristicQuestionTypes, QuestionType.short];

const _methodHints = {
  GenerationMethod.heuristic: 'Built offline from your wiki pages (no AI).',
  GenerationMethod.llm:
      'Written by your AI model from the wiki pages. Runs in the background.',
  GenerationMethod.hybrid:
      'Offline cards refined by your AI model. Runs in the background.',
};

Future<void> showGenerateStudyDialog(
  BuildContext context, {
  StudyMaterialKind kind = StudyMaterialKind.flashcards,
}) {
  return showDialog<void>(
    context: context,
    builder: (_) => GenerateStudyDialog(initialKind: kind),
  );
}

class GenerateStudyDialog extends ConsumerStatefulWidget {
  const GenerateStudyDialog({
    super.key,
    this.initialKind = StudyMaterialKind.flashcards,
  });

  final StudyMaterialKind initialKind;

  @override
  ConsumerState<GenerateStudyDialog> createState() =>
      _GenerateStudyDialogState();
}

class _GenerateStudyDialogState extends ConsumerState<GenerateStudyDialog> {
  late StudyMaterialKind _kind = widget.initialKind;
  _ScopeType _scope = _ScopeType.wholeClass;
  final _topicController = TextEditingController();
  final _nameController = TextEditingController();
  String? _fileId;
  int _cardCount = 30;
  int _questionCount = 10;
  final Set<CardType> _cardTypes = {CardType.basic, CardType.cloze};
  final Set<QuestionType> _questionTypes = {..._aiQuestionTypes};

  /// Null until the user picks one: then AI when reachable, otherwise offline.
  GenerationMethod? _chosenMethod;
  bool _aiGrading = true;
  bool _busy = false;
  Object? _error;

  @override
  void dispose() {
    _topicController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  bool get _isFlashcards => _kind == StudyMaterialKind.flashcards;

  GenerationMethod _method(bool aiReady) => aiReady
      ? _chosenMethod ?? GenerationMethod.llm
      : GenerationMethod.heuristic;

  List<QuestionType> _selectedQuestionTypes(GenerationMethod method) =>
      (method.usesAi ? _aiQuestionTypes : _heuristicQuestionTypes)
          .where(_questionTypes.contains)
          .toList();

  StudyScope? _buildScope(String? currentPage) {
    switch (_scope) {
      case _ScopeType.wholeClass:
        return const StudyScope.wholeClass();
      case _ScopeType.topic:
        final topic = _topicController.text.trim();
        return topic.isEmpty ? null : StudyScope.topic(topic);
      case _ScopeType.currentPage:
        return currentPage == null ? null : StudyScope.pages([currentPage]);
      case _ScopeType.file:
        return _fileId == null ? null : StudyScope.file(_fileId!);
    }
  }

  bool _typesValid(GenerationMethod method) => _isFlashcards
      ? _cardTypes.isNotEmpty
      : _selectedQuestionTypes(method).isNotEmpty;

  String _jobLabel(StudyScope scope, String? name) {
    if (name != null) return name;
    final what = _isFlashcards ? 'flashcards' : 'quiz';
    return switch (scope.type) {
      'topic' => '${scope.query} $what',
      'class' => 'All pages $what',
      _ => 'New $what',
    };
  }

  Future<void> _generate(
    String classId,
    StudyScope scope,
    GenerationMethod method,
  ) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(apiClientProvider);
    final messenger = ScaffoldMessenger.of(context);
    final name = _nameController.text.trim().isEmpty
        ? null
        : _nameController.text.trim();
    final kind = _isFlashcards ? StudyKind.deck : StudyKind.quiz;
    try {
      final GenerationStart start;
      if (_isFlashcards) {
        start = await api.generateDeck(
          classId,
          scope: scope,
          count: _cardCount,
          cardTypes: _cardTypes.toList(),
          method: method,
          name: name,
        );
      } else {
        start = await api.generateQuiz(
          classId,
          scope: scope,
          count: _questionCount,
          questionTypes: _selectedQuestionTypes(method),
          method: method,
          aiGrading: _aiGrading,
          name: name,
        );
      }
      ref.read(sidebarModeProvider.notifier).state = SidebarMode.study;
      if (start.taskId case final taskId?) {
        ref
            .read(studyJobsProvider.notifier)
            .track(
              StudyJob(
                taskId: taskId,
                classId: classId,
                kind: kind,
                label: _jobLabel(scope, name),
              ),
            );
        messenger.showSnackBar(
          const SnackBar(
            content: Text(
              'Writing with AI in the background. Progress shows in the '
              'Study tab.',
            ),
          ),
        );
      } else {
        ref.invalidate(
          kind == StudyKind.deck
              ? deckListProvider(classId)
              : quizListProvider(classId),
        );
        ref.read(studySelectionProvider.notifier).state = StudySelection(
          kind,
          start.id!,
        );
      }
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final classId = ref.watch(currentClassIdProvider);
    final currentPage = ref.watch(currentWikiPagePathProvider);
    final files = classId == null
        ? const <SourceFile>[]
        : ref.watch(fileListProvider(classId)).valueOrNull ?? const [];
    final pages = classId == null
        ? const <WikiPageSummary>[]
        : ref.watch(wikiTreeProvider(classId)).valueOrNull ?? const [];
    final currentTitle = pages
        .where((p) => p.path == currentPage)
        .map((p) => p.title)
        .firstOrNull;
    final scope = _buildScope(currentPage);
    final aiStatus = ref.watch(llmConnectionStatusProvider);
    final aiReady = aiStatus.valueOrNull?.connected ?? false;
    final method = _method(aiReady);
    final canGenerate =
        classId != null && scope != null && _typesValid(method) && !_busy;
    final questionTypes = method.usesAi
        ? _aiQuestionTypes
        : _heuristicQuestionTypes;
    final showAiGrading =
        !_isFlashcards &&
        method.usesAi &&
        _questionTypes.contains(QuestionType.short);
    final methodSelector = SegmentedButton<GenerationMethod>(
      showSelectedIcon: false,
      segments: [
        for (final m in GenerationMethod.values)
          ButtonSegment(
            value: m,
            label: Text(m.label),
            enabled: !m.usesAi || aiReady,
          ),
      ],
      selected: {method},
      onSelectionChanged: _busy
          ? null
          : (s) => setState(() => _chosenMethod = s.first),
    );

    return AlertDialog(
      title: const Text('Create study material'),
      content: SizedBox(
        width: 440,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SegmentedButton<StudyMaterialKind>(
                segments: const [
                  ButtonSegment(
                    value: StudyMaterialKind.flashcards,
                    icon: Icon(Icons.style_outlined),
                    label: Text('Flashcards'),
                  ),
                  ButtonSegment(
                    value: StudyMaterialKind.quiz,
                    icon: Icon(Icons.quiz_outlined),
                    label: Text('Practice quiz'),
                  ),
                ],
                selected: {_kind},
                onSelectionChanged: _busy
                    ? null
                    : (s) => setState(() => _kind = s.first),
              ),
              const SizedBox(height: 16),
              Text('How', style: theme.textTheme.labelLarge),
              const SizedBox(height: 4),
              if (aiReady)
                methodSelector
              else
                Tooltip(
                  message: aiStatus.isLoading
                      ? 'Checking your AI provider...'
                      : 'No AI model is reachable. Configure one in the sidebar.',
                  child: methodSelector,
                ),
              const SizedBox(height: 16),
              Text('From', style: theme.textTheme.labelLarge),
              const SizedBox(height: 4),
              DropdownButton<_ScopeType>(
                isExpanded: true,
                value: _scope,
                onChanged: _busy
                    ? null
                    : (v) => setState(() => _scope = v ?? _scope),
                items: [
                  const DropdownMenuItem(
                    value: _ScopeType.wholeClass,
                    child: Text('Whole class'),
                  ),
                  const DropdownMenuItem(
                    value: _ScopeType.topic,
                    child: Text('A topic'),
                  ),
                  DropdownMenuItem(
                    value: _ScopeType.currentPage,
                    enabled: currentPage != null,
                    child: Text(
                      currentTitle == null
                          ? 'Current wiki page (none open)'
                          : 'Current page: $currentTitle',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem(
                    value: _ScopeType.file,
                    enabled: files.isNotEmpty,
                    child: const Text('A source file'),
                  ),
                ],
              ),
              if (_scope == _ScopeType.topic)
                TextField(
                  controller: _topicController,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: 'Topic',
                    hintText: 'e.g. Viterbi decoding',
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              if (_scope == _ScopeType.file)
                DropdownButton<String>(
                  isExpanded: true,
                  hint: const Text('Choose a file'),
                  value: _fileId,
                  onChanged: (v) => setState(() => _fileId = v),
                  items: [
                    for (final f in files)
                      DropdownMenuItem(
                        value: f.id,
                        child: Text(
                          f.originalFilename,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                ),
              const SizedBox(height: 16),
              Text(
                _isFlashcards ? 'Card types' : 'Question types',
                style: theme.textTheme.labelLarge,
              ),
              const SizedBox(height: 4),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: _isFlashcards
                    ? [
                        _typeChip(
                          'Question & answer',
                          _cardTypes,
                          CardType.basic,
                        ),
                        _typeChip(
                          'Fill-in (cloze)',
                          _cardTypes,
                          CardType.cloze,
                        ),
                      ]
                    : [
                        for (final t in questionTypes)
                          _typeChip(t.label, _questionTypes, t),
                      ],
              ),
              if (showAiGrading)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  title: const Text('Grade short answers with AI'),
                  subtitle: const Text(
                    'When off, you compare your answer with the model answer.',
                  ),
                  value: _aiGrading,
                  onChanged: _busy
                      ? null
                      : (v) => setState(() => _aiGrading = v),
                ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Text(
                    _isFlashcards ? 'Up to' : 'Questions',
                    style: theme.textTheme.labelLarge,
                  ),
                  const SizedBox(width: 12),
                  DropdownButton<int>(
                    value: _isFlashcards ? _cardCount : _questionCount,
                    onChanged: _busy
                        ? null
                        : (v) => setState(() {
                            if (v == null) return;
                            _isFlashcards ? _cardCount = v : _questionCount = v;
                          }),
                    items: [
                      for (final n
                          in _isFlashcards ? _cardCounts : _questionCounts)
                        DropdownMenuItem(value: n, child: Text('$n')),
                    ],
                  ),
                  if (_isFlashcards) ...[
                    const SizedBox(width: 8),
                    const Text('cards'),
                  ],
                ],
              ),
              TextField(
                controller: _nameController,
                decoration: const InputDecoration(labelText: 'Name (optional)'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(
                    method.usesAi
                        ? Icons.auto_awesome_outlined
                        : Icons.offline_bolt_outlined,
                    size: 16,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      _methodHints[method]!,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                ErrorCard(error: _error!),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: canGenerate
              ? () => _generate(classId, scope, method)
              : null,
          child: _busy
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Generate'),
        ),
      ],
    );
  }

  Widget _typeChip<T>(String label, Set<T> selected, T value) {
    return FilterChip(
      label: Text(label),
      selected: selected.contains(value),
      onSelected: _busy
          ? null
          : (on) => setState(
              () => on ? selected.add(value) : selected.remove(value),
            ),
    );
  }
}
