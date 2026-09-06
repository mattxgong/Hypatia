const maxClassNameLength = 255;
const maxClassDescriptionLength = 4000;
const maxModelNameLength = 255;
const maxApiKeyLength = 8192;
const maxBaseUrlLength = 2048;

String? validateClassName(String? value) {
  final name = value?.trim() ?? '';
  if (name.isEmpty) return 'Enter a class name.';
  if (name.length > maxClassNameLength) {
    return 'Use $maxClassNameLength characters or fewer.';
  }
  return null;
}

String? validateClassDescription(String? value) {
  if ((value ?? '').trim().length > maxClassDescriptionLength) {
    return 'Use $maxClassDescriptionLength characters or fewer.';
  }
  return null;
}

String? validateModelName(String? value) {
  if ((value ?? '').trim().length > maxModelNameLength) {
    return 'Use $maxModelNameLength characters or fewer.';
  }
  return null;
}

String? validateApiKey(String? value) {
  if ((value ?? '').length > maxApiKeyLength) {
    return 'Use $maxApiKeyLength characters or fewer.';
  }
  return null;
}

String? validateOllamaBaseUrl(String? value) {
  final input = value?.trim() ?? '';
  if (input.isEmpty) return 'Enter the Ollama server URL.';
  if (input.length > maxBaseUrlLength) {
    return 'Use $maxBaseUrlLength characters or fewer.';
  }
  final uri = Uri.tryParse(input);
  if (uri == null ||
      !const {'http', 'https'}.contains(uri.scheme) ||
      uri.host.isEmpty) {
    return 'Enter a valid HTTP or HTTPS URL.';
  }
  return null;
}
