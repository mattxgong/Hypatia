# Machine Learning Basics

## Introduction

Machine learning is a subset of artificial intelligence that enables systems to learn
from data without being explicitly programmed. This chapter covers the fundamental concepts
needed to understand modern ML systems.

## Supervised Learning

Supervised learning uses labeled training data to learn a mapping from inputs to outputs.
Common algorithms include:

- **Linear Regression**: Predicts continuous values by fitting a linear model.
- **Logistic Regression**: Classifies inputs into discrete categories using a sigmoid function.
- **Decision Trees**: Recursively splits the feature space based on information gain.
- **Random Forests**: An ensemble of decision trees that reduces overfitting.

The goal is to minimize a loss function that measures the difference between predictions
and true labels.

## Neural Networks

Neural networks are composed of layers of interconnected neurons. Each neuron applies
a weighted sum followed by a non-linear activation function.

Key components:
- **Input layer**: Receives the raw features.
- **Hidden layers**: Transform features through learned weights.
- **Output layer**: Produces the final prediction.
- **Activation functions**: ReLU, sigmoid, tanh introduce non-linearity.

Training uses backpropagation to compute gradients of the loss with respect to each weight,
then gradient descent to update the weights.

## Overfitting and Regularization

Overfitting occurs when a model memorizes training data rather than learning general patterns.
Signs include high training accuracy but low test accuracy.

Regularization techniques:
- **L1 regularization** (Lasso): Adds absolute weight penalty, encourages sparsity.
- **L2 regularization** (Ridge): Adds squared weight penalty, prevents large weights.
- **Dropout**: Randomly disables neurons during training to prevent co-adaptation.
- **Early stopping**: Halts training when validation loss stops improving.

## Evaluation Metrics

- **Accuracy**: Fraction of correct predictions. Misleading for imbalanced datasets.
- **Precision**: Of predicted positives, how many are truly positive.
- **Recall**: Of actual positives, how many were correctly predicted.
- **F1 Score**: Harmonic mean of precision and recall.
- **AUC-ROC**: Area under the receiver operating characteristic curve.
