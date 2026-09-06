import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/utils/input_validation.dart';

void main() {
  test('class names are required and bounded', () {
    expect(validateClassName('  '), isNotNull);
    expect(validateClassName('x' * maxClassNameLength), isNull);
    expect(validateClassName('x' * (maxClassNameLength + 1)), isNotNull);
  });

  test('class descriptions use the server maximum', () {
    expect(validateClassDescription(''), isNull);
    expect(
      validateClassDescription('x' * (maxClassDescriptionLength + 1)),
      isNotNull,
    );
  });

  test('Ollama URLs require HTTP or HTTPS with a host', () {
    expect(validateOllamaBaseUrl('http://localhost:11434'), isNull);
    expect(validateOllamaBaseUrl('https://ollama.example.test'), isNull);
    expect(validateOllamaBaseUrl('localhost:11434'), isNotNull);
    expect(validateOllamaBaseUrl('file:///tmp/ollama'), isNotNull);
  });

  test('model names and API keys use server limits', () {
    expect(validateModelName('x' * (maxModelNameLength + 1)), isNotNull);
    expect(validateApiKey('x' * (maxApiKeyLength + 1)), isNotNull);
    expect(validateApiKey(''), isNull);
  });
}
