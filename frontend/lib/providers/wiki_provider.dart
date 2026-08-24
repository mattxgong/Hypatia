import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/wiki_page.dart';

final wikiTreeProvider = Provider.family<List<WikiPageSummary>, String>((
  ref,
  classId,
) {
  return _mockWikiTreeByClass[classId] ?? [];
});

final currentWikiPagePathProvider = StateProvider<String?>((ref) => null);

final currentWikiPageProvider = Provider<WikiPage?>((ref) {
  final path = ref.watch(currentWikiPagePathProvider);
  if (path == null) return null;
  return _mockPages[path];
});

const _mockWikiTreeByClass = <String, List<WikiPageSummary>>{
  'class-1': [
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
  ],
  'class-2': [
    WikiPageSummary(
      path: 'class2/index',
      title: 'Index',
      category: WikiCategory.wikiIndex,
    ),
    WikiPageSummary(
      path: 'class2/pages/source-summaries/organic-reactions',
      title: 'Organic Reactions Overview',
      category: WikiCategory.sourceSummary,
    ),
    WikiPageSummary(
      path: 'class2/pages/concepts/functional-groups',
      title: 'Functional Groups',
      category: WikiCategory.concept,
    ),
    WikiPageSummary(
      path: 'class2/pages/concepts/stereochemistry',
      title: 'Stereochemistry',
      category: WikiCategory.concept,
    ),
  ],
};

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
  'pages/concepts/backpropagation': WikiPage(
    path: 'pages/concepts/backpropagation',
    title: 'Backpropagation',
    category: WikiCategory.concept,
    content: '''# Backpropagation

Backpropagation is the algorithm used to compute gradients of the loss
function with respect to each weight in a neural network.

## How it Works

1. **Forward pass**: compute predictions and loss
2. **Backward pass**: propagate error gradients from output to input
3. **Update**: adjust weights using gradient descent

## Chain Rule

Backpropagation relies on the chain rule of calculus to efficiently compute
partial derivatives through each layer.

## Citations

Covered in [Lecture 2](hypatia://cite?file=lecture-2.mp4&loc=t:120).
''',
    updatedAt: DateTime(2024, 9, 13),
  ),
  'pages/source-summaries/lecture-1': WikiPage(
    path: 'pages/source-summaries/lecture-1',
    title: 'Lecture 1 — Intro to ML',
    category: WikiCategory.sourceSummary,
    content: '''# Lecture 1 — Introduction to Machine Learning

## Overview

This lecture introduces the fundamental concepts of machine learning,
including supervised and unsupervised learning paradigms.

## Key Topics

- What is machine learning?
- Supervised vs. unsupervised learning
- Regression and classification
- Introduction to neural networks

## Summary

The lecture provides a high-level overview of the ML landscape and sets the
stage for deeper dives into specific algorithms in subsequent lectures.
''',
    updatedAt: DateTime(2024, 9, 10),
  ),
  'pages/source-summaries/lecture-2': WikiPage(
    path: 'pages/source-summaries/lecture-2',
    title: 'Lecture 2 — Linear Regression',
    category: WikiCategory.sourceSummary,
    content: '''# Lecture 2 — Linear Regression

## Overview

This lecture covers linear regression, the simplest supervised learning
algorithm for predicting continuous values.

## Key Topics

- Hypothesis function: h(x) = θ₀ + θ₁x
- Cost function (MSE)
- Gradient descent algorithm
- Normal equation

## Summary

Linear regression serves as the foundation for understanding more complex
models. The gradient descent optimization technique introduced here is reused
throughout the course.
''',
    updatedAt: DateTime(2024, 9, 11),
  ),
  'pages/entities/geoffrey-hinton': WikiPage(
    path: 'pages/entities/geoffrey-hinton',
    title: 'Geoffrey Hinton',
    category: WikiCategory.entity,
    content: '''# Geoffrey Hinton

Geoffrey Hinton is a computer scientist and cognitive psychologist, known as
one of the "Godfathers of Deep Learning."

## Contributions

- **Backpropagation**: popularized the algorithm for training neural networks
- **Boltzmann machines**: co-invented with Terry Sejnowski
- **Deep belief networks**: pioneered layer-wise pre-training
- **Dropout**: regularization technique to prevent overfitting

## Recognition

- 2018 Turing Award (shared with Yoshua Bengio and Yann LeCun)
- Fellow of the Royal Society

## References

Mentioned in [Lecture 1](hypatia://cite?file=lecture-1.mp4&loc=t:85).
''',
    updatedAt: DateTime(2024, 9, 12),
  ),
  'class2/index': WikiPage(
    path: 'class2/index',
    title: 'Index',
    category: WikiCategory.wikiIndex,
    content: '''# Organic Chemistry Wiki

## Source Summaries
- [[Organic Reactions Overview]]

## Concepts
- [[Functional Groups]]
- [[Stereochemistry]]
''',
    updatedAt: DateTime(2024, 9, 10),
  ),
  'class2/pages/source-summaries/organic-reactions': WikiPage(
    path: 'class2/pages/source-summaries/organic-reactions',
    title: 'Organic Reactions Overview',
    category: WikiCategory.sourceSummary,
    content: '''# Organic Reactions Overview

## Reaction Types

- **Substitution**: one group replaces another (SN1, SN2)
- **Elimination**: atoms removed to form double bond (E1, E2)
- **Addition**: atoms added across a double bond
- **Rearrangement**: carbon skeleton reorganizes

## Key Reagents

Common reagents and their roles in organic synthesis.
''',
    updatedAt: DateTime(2024, 9, 8),
  ),
  'class2/pages/concepts/functional-groups': WikiPage(
    path: 'class2/pages/concepts/functional-groups',
    title: 'Functional Groups',
    category: WikiCategory.concept,
    content: '''# Functional Groups

Functional groups determine the chemical behavior of organic molecules.

## Common Groups

| Group | Formula | Example |
|-------|---------|---------|
| Hydroxyl | -OH | Ethanol |
| Carboxyl | -COOH | Acetic acid |
| Amino | -NH₂ | Glycine |
| Carbonyl | C=O | Acetone |
''',
    updatedAt: DateTime(2024, 9, 9),
  ),
  'class2/pages/concepts/stereochemistry': WikiPage(
    path: 'class2/pages/concepts/stereochemistry',
    title: 'Stereochemistry',
    category: WikiCategory.concept,
    content: '''# Stereochemistry

The study of the 3D arrangement of atoms in molecules.

## Key Concepts

- **Chirality**: non-superimposable mirror images
- **Enantiomers**: mirror-image stereoisomers
- **Diastereomers**: non-mirror-image stereoisomers
- **R/S nomenclature**: Cahn-Ingold-Prelog priority rules
''',
    updatedAt: DateTime(2024, 9, 9),
  ),
};
