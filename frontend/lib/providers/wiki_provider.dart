import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/wiki_page.dart';

final wikiTreeProvider = Provider.family<List<WikiPageSummary>, String>((
  ref,
  classId,
) {
  return _mockWikiTree;
});

final currentWikiPagePathProvider = StateProvider<String?>((ref) => null);

final currentWikiPageProvider = Provider<WikiPage?>((ref) {
  final path = ref.watch(currentWikiPagePathProvider);
  if (path == null) return null;
  return _mockPages[path];
});

const _mockWikiTree = [
  WikiPageSummary(
    path: 'index',
    title: 'Index',
    category: WikiCategory.wikiIndex,
  ),
  WikiPageSummary(
    path: 'pages/source-summaries/lecture-1',
    title: 'Lecture 1 — Intro to ML',
    category: WikiCategory.sourceSummary,
  ),
  WikiPageSummary(
    path: 'pages/source-summaries/lecture-2',
    title: 'Lecture 2 — Linear Regression',
    category: WikiCategory.sourceSummary,
  ),
  WikiPageSummary(
    path: 'pages/concepts/neural-networks',
    title: 'Neural Networks',
    category: WikiCategory.concept,
  ),
  WikiPageSummary(
    path: 'pages/concepts/backpropagation',
    title: 'Backpropagation',
    category: WikiCategory.concept,
  ),
  WikiPageSummary(
    path: 'pages/entities/geoffrey-hinton',
    title: 'Geoffrey Hinton',
    category: WikiCategory.entity,
  ),
];

final _mockPages = <String, WikiPage>{
  'index': WikiPage(
    path: 'index',
    title: 'Index',
    category: WikiCategory.wikiIndex,
    content: '''# Machine Learning Wiki

## Source Summaries
- [[Lecture 1 — Intro to ML]]
- [[Lecture 2 — Linear Regression]]

## Concepts
- [[Neural Networks]]
- [[Backpropagation]]

## Entities
- [[Geoffrey Hinton]]
''',
    updatedAt: DateTime(2024, 9, 15),
  ),
  'pages/concepts/neural-networks': WikiPage(
    path: 'pages/concepts/neural-networks',
    title: 'Neural Networks',
    category: WikiCategory.concept,
    content: '''# Neural Networks

A neural network is a computational model inspired by the structure of
biological neural networks in the brain.

## Architecture

Neural networks consist of layers of interconnected nodes (neurons):
- **Input layer**: receives raw data
- **Hidden layers**: perform transformations
- **Output layer**: produces predictions

## Key Concepts

1. **Activation functions**: ReLU, sigmoid, tanh
2. **Forward propagation**: data flows input → output
3. **Backpropagation**: gradients flow output → input

## Citations

First introduced in the course in [Lecture 1](hypatia://cite?file=lecture-1.mp4&loc=t:342).
''',
    updatedAt: DateTime(2024, 9, 14),
  ),
};
