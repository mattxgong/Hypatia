import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/study.dart';
import '../../providers/study_provider.dart';
import '../../services/api_client.dart';

void _snack(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}

/// `format` is `csv` (generic, Quizlet) or `anki` (Anki import file).
Future<void> exportDeck(
  BuildContext context,
  WidgetRef ref,
  Deck deck,
  String format,
) async {
  try {
    final bytes = await ref
        .read(apiClientProvider)
        .exportDeck(deck.classId, deck.id, format: format);
    final safeName = deck.name.replaceAll(RegExp(r'[^\w\-. ]'), '_');
    final isCsv = format == 'csv';
    final saved = await FilePicker.saveFile(
      dialogTitle: isCsv ? 'Export deck as CSV' : 'Export deck for Anki',
      fileName: isCsv ? '$safeName.csv' : '$safeName.anki.txt',
      bytes: bytes,
      type: FileType.custom,
      allowedExtensions: [isCsv ? 'csv' : 'txt'],
    );
    if (saved != null && context.mounted) {
      _snack(
        context,
        isCsv
            ? 'Deck exported'
            : 'Deck exported. In Anki, use File > Import to add it.',
      );
    }
  } on ApiException catch (e) {
    if (context.mounted) _snack(context, 'Export failed: ${e.detail}');
  }
}

Future<bool> _confirmDelete(BuildContext context, String what) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text('Delete $what?'),
      content: const Text('This cannot be undone.'),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('Delete'),
        ),
      ],
    ),
  );
  return confirmed ?? false;
}

Future<void> deleteDeck(BuildContext context, WidgetRef ref, Deck deck) async {
  if (!await _confirmDelete(context, '"${deck.name}" and its cards')) return;
  try {
    await ref.read(apiClientProvider).deleteDeck(deck.classId, deck.id);
    if (ref.read(studySelectionProvider) ==
        StudySelection(StudyKind.deck, deck.id)) {
      ref.read(studySelectionProvider.notifier).state = null;
    }
    ref.invalidate(deckListProvider(deck.classId));
  } on ApiException catch (e) {
    if (context.mounted) _snack(context, 'Delete failed: ${e.detail}');
  }
}

Future<void> deleteQuiz(
  BuildContext context,
  WidgetRef ref,
  QuizSummary quiz,
) async {
  if (!await _confirmDelete(context, '"${quiz.name}" and its attempts')) return;
  try {
    await ref.read(apiClientProvider).deleteQuiz(quiz.classId, quiz.id);
    if (ref.read(studySelectionProvider) ==
        StudySelection(StudyKind.quiz, quiz.id)) {
      ref.read(studySelectionProvider.notifier).state = null;
    }
    ref.invalidate(quizListProvider(quiz.classId));
  } on ApiException catch (e) {
    if (context.mounted) _snack(context, 'Delete failed: ${e.detail}');
  }
}
