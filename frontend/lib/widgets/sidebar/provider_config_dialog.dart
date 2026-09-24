import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/settings_provider.dart';
import '../../services/api_client.dart';
import '../../utils/input_validation.dart';
import '../common/provider_icon.dart';

Future<bool> showProviderConfigDialog(
  BuildContext context,
  String providerId, {
  bool activateProvider = false,
}) async {
  return await showDialog<bool>(
        context: context,
        builder: (_) => ProviderConfigDialog(
          providerId: providerId,
          activateProvider: activateProvider,
        ),
      ) ??
      false;
}

class ProviderConfigDialog extends ConsumerStatefulWidget {
  const ProviderConfigDialog({
    super.key,
    required this.providerId,
    this.activateProvider = false,
  });

  final String providerId;
  final bool activateProvider;

  @override
  ConsumerState<ProviderConfigDialog> createState() =>
      _ProviderConfigDialogState();
}

class _ProviderConfigDialogState extends ConsumerState<ProviderConfigDialog> {
  final _formKey = GlobalKey<FormState>();
  final _apiKeyController = TextEditingController();
  final _modelController = TextEditingController();
  final _baseUrlController = TextEditingController();
  bool _saving = false;
  bool _obscureKey = true;
  List<String> _ollamaModels = [];
  bool _loadingModels = false;
  bool _testing = false;
  bool? _testResult;
  String? _testError;
  bool _hasStoredApiKey = false;
  bool _clearStoredApiKey = false;

  @override
  void initState() {
    super.initState();
    _apiKeyController.addListener(_onApiKeyChanged);
    _loadCurrentSettings();
  }

  Future<void> _loadCurrentSettings() async {
    final settings = await ref.read(fullSettingsProvider.future);
    if (!mounted) return;
    final models = settings['llm_models'] as Map<String, dynamic>?;
    _modelController.text = (models?[widget.providerId] as String?) ?? '';

    String? masked;
    switch (widget.providerId) {
      case 'anthropic':
        masked = settings['anthropic_api_key'] as String?;
      case 'openai':
        masked = settings['openai_api_key'] as String?;
      case 'copilot':
        masked = settings['github_token'] as String?;
      case 'ollama':
      case 'copilot-ollama':
        _baseUrlController.text =
            (settings['ollama_base_url'] as String?) ??
            'http://localhost:11434';
    }
    setState(() => _hasStoredApiKey = masked != null);
  }

  void _onApiKeyChanged() {
    if (_apiKeyController.text.isNotEmpty && _clearStoredApiKey) {
      setState(() => _clearStoredApiKey = false);
    }
  }

  @override
  void dispose() {
    _apiKeyController.removeListener(_onApiKeyChanged);
    _apiKeyController.dispose();
    _modelController.dispose();
    _baseUrlController.dispose();
    super.dispose();
  }

  String get _title {
    switch (widget.providerId) {
      case 'copilot':
        return 'GitHub Copilot';
      case 'anthropic':
        return 'Anthropic Claude';
      case 'openai':
        return 'OpenAI';
      case 'ollama':
        return 'Ollama (Local)';
      case 'copilot-ollama':
        return 'Copilot + Ollama';
      default:
        return 'Provider';
    }
  }

  bool get _needsApiKey =>
      widget.providerId == 'anthropic' ||
      widget.providerId == 'openai' ||
      widget.providerId == 'copilot';

  bool get _needsBaseUrl =>
      widget.providerId == 'ollama' || widget.providerId == 'copilot-ollama';

  String get _apiKeyLabel {
    switch (widget.providerId) {
      case 'anthropic':
        return 'Anthropic API Key';
      case 'openai':
        return 'OpenAI API Key';
      case 'copilot':
        return 'GitHub Token (optional)';
      default:
        return 'API Key';
    }
  }

  String get _apiKeyHint {
    switch (widget.providerId) {
      case 'anthropic':
        return 'sk-ant-...';
      case 'openai':
        return 'sk-...';
      case 'copilot':
        return 'ghp_... or leave empty for CLI auth';
      default:
        return '';
    }
  }

  String get _defaultModel {
    switch (widget.providerId) {
      case 'copilot':
        return 'gpt-5.4';
      case 'anthropic':
        return 'claude-sonnet-4-20250514';
      case 'openai':
        return 'gpt-4o';
      case 'ollama':
      case 'copilot-ollama':
        return 'llama3.2';
      default:
        return '';
    }
  }

  Future<void> _fetchOllamaModels() async {
    final urlError = validateOllamaBaseUrl(_baseUrlController.text);
    if (urlError != null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(urlError)));
      return;
    }
    setState(() => _loadingModels = true);
    try {
      final apiClient = ref.read(apiClientProvider);
      if (_baseUrlController.text.isNotEmpty) {
        await ref
            .read(fullSettingsProvider.notifier)
            .updateFields(ollamaBaseUrl: _baseUrlController.text.trim());
      }
      final models = await apiClient.getOllamaModels();
      if (mounted) {
        setState(() {
          _ollamaModels = models;
          _loadingModels = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _loadingModels = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Could not reach Ollama: $e')));
      }
    }
  }

  Future<void> _testConnection() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final key = _apiKeyController.text.trim();
    setState(() {
      _testing = true;
      _testResult = null;
      _testError = null;
    });
    try {
      final apiClient = ref.read(apiClientProvider);
      final result = await apiClient.testConnection(
        widget.providerId,
        apiKey: !_needsApiKey
            ? null
            : key.isNotEmpty
            ? key
            : (_clearStoredApiKey ? '' : null),
        model: _modelController.text.trim(),
        ollamaBaseUrl: _needsBaseUrl ? _baseUrlController.text.trim() : null,
      );
      if (mounted) {
        setState(() {
          _testing = false;
          _testResult = result.valid;
          _testError = result.error;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _testing = false;
          _testResult = false;
          _testError = e is ApiException ? e.detail : e.toString();
        });
      }
    }
  }

  void _clearTestResult() {
    if (_testResult == null) return;
    setState(() {
      _testResult = null;
      _testError = null;
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      final notifier = ref.read(fullSettingsProvider.notifier);

      final model = _modelController.text.trim();
      final apiKey = _apiKeyController.text.trim();
      final baseUrl = _baseUrlController.text.trim();
      final apiKeyUpdate = _clearStoredApiKey
          ? ''
          : (apiKey.isNotEmpty ? apiKey : null);

      switch (widget.providerId) {
        case 'anthropic':
          await notifier.updateFields(
            llmProvider: widget.activateProvider ? widget.providerId : null,
            anthropicApiKey: apiKeyUpdate,
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'openai':
          await notifier.updateFields(
            llmProvider: widget.activateProvider ? widget.providerId : null,
            openaiApiKey: apiKeyUpdate,
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'copilot':
          await notifier.updateFields(
            llmProvider: widget.activateProvider ? widget.providerId : null,
            githubToken: apiKeyUpdate,
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'ollama':
          await notifier.updateFields(
            llmProvider: widget.activateProvider ? widget.providerId : null,
            ollamaBaseUrl: baseUrl.isNotEmpty
                ? baseUrl
                : 'http://localhost:11434',
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'copilot-ollama':
          await notifier.updateFields(
            llmProvider: widget.activateProvider ? widget.providerId : null,
            ollamaBaseUrl: baseUrl.isNotEmpty
                ? baseUrl
                : 'http://localhost:11434',
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
      }

      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Failed to save: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return AlertDialog(
      scrollable: true,
      title: Row(
        children: [
          ProviderIcon(providerId: widget.providerId, size: 24),
          const SizedBox(width: 10),
          Text(_title),
        ],
      ),
      content: SizedBox(
        width: 400,
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (widget.providerId == 'copilot') ...[
                Text(
                  'GitHub Copilot uses CLI-based authentication by default. '
                  'You can optionally provide a GitHub token.',
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 16),
              ],
              if (_needsApiKey) ...[
                TextFormField(
                  controller: _apiKeyController,
                  obscureText: _obscureKey,
                  decoration: InputDecoration(
                    labelText: _apiKeyLabel,
                    hintText: _apiKeyHint,
                    border: const OutlineInputBorder(),
                    suffixIcon: IconButton(
                      icon: Icon(
                        _obscureKey ? Icons.visibility_off : Icons.visibility,
                      ),
                      onPressed: () =>
                          setState(() => _obscureKey = !_obscureKey),
                    ),
                  ),
                  maxLength: maxApiKeyLength,
                  validator: validateApiKey,
                  onChanged: (_) => _clearTestResult(),
                ),
                if (_hasStoredApiKey && _apiKeyController.text.isEmpty) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _clearStoredApiKey
                              ? 'Saved key will be removed'
                              : 'A saved key is configured',
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                      TextButton(
                        onPressed: () {
                          setState(() {
                            _clearStoredApiKey = !_clearStoredApiKey;
                            _testResult = null;
                            _testError = null;
                          });
                        },
                        child: Text(
                          _clearStoredApiKey
                              ? 'Keep saved key'
                              : 'Clear saved key',
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 16),
              ],
              if (_needsBaseUrl) ...[
                TextFormField(
                  controller: _baseUrlController,
                  decoration: const InputDecoration(
                    labelText: 'Ollama Base URL',
                    hintText: 'http://localhost:11434',
                    border: OutlineInputBorder(),
                  ),
                  maxLength: maxBaseUrlLength,
                  validator: validateOllamaBaseUrl,
                  onChanged: (_) => _clearTestResult(),
                ),
                const SizedBox(height: 16),
              ],
              TextFormField(
                controller: _modelController,
                decoration: InputDecoration(
                  labelText: 'Model',
                  hintText: _defaultModel,
                  border: const OutlineInputBorder(),
                ),
                maxLength: maxModelNameLength,
                validator: validateModelName,
                onChanged: (_) => _clearTestResult(),
              ),
              if (_needsBaseUrl) ...[
                const SizedBox(height: 12),
                Row(
                  children: [
                    OutlinedButton.icon(
                      onPressed: _loadingModels ? null : _fetchOllamaModels,
                      icon: _loadingModels
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.refresh, size: 16),
                      label: const Text('Fetch Models'),
                    ),
                  ],
                ),
                if (_ollamaModels.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  SizedBox(
                    height: 120,
                    child: ListView.builder(
                      shrinkWrap: true,
                      itemCount: _ollamaModels.length,
                      itemBuilder: (context, index) {
                        final model = _ollamaModels[index];
                        return ListTile(
                          dense: true,
                          title: Text(model, style: theme.textTheme.bodySmall),
                          onTap: () {
                            _modelController.text = model;
                          },
                          selected: _modelController.text == model,
                        );
                      },
                    ),
                  ),
                ],
              ],
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  OutlinedButton.icon(
                    onPressed: _testing ? null : _testConnection,
                    icon: _testing
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.wifi_tethering, size: 16),
                    label: const Text('Test Connection'),
                  ),
                  if (_testResult != null) ...[
                    const SizedBox(width: 8),
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Icon(
                        _testResult! ? Icons.check_circle : Icons.cancel,
                        color: _testResult! ? Colors.green : Colors.red,
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.only(top: 9),
                        child: Text(
                          _testResult!
                              ? 'Connected'
                              : (_testError ?? 'Connection failed'),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: _testResult! ? Colors.green : Colors.red,
                          ),
                          maxLines: 4,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Save'),
        ),
      ],
    );
  }
}
