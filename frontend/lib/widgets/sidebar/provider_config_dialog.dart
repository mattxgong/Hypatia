import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/settings_provider.dart';
import '../../services/api_client.dart';
import '../common/provider_icon.dart';

void showProviderConfigDialog(BuildContext context, String providerId) {
  showDialog<void>(
    context: context,
    builder: (_) => ProviderConfigDialog(providerId: providerId),
  );
}

class ProviderConfigDialog extends ConsumerStatefulWidget {
  const ProviderConfigDialog({super.key, required this.providerId});

  final String providerId;

  @override
  ConsumerState<ProviderConfigDialog> createState() =>
      _ProviderConfigDialogState();
}

class _ProviderConfigDialogState extends ConsumerState<ProviderConfigDialog> {
  final _apiKeyController = TextEditingController();
  final _modelController = TextEditingController();
  final _baseUrlController = TextEditingController();
  bool _saving = false;
  bool _obscureKey = true;
  List<String> _ollamaModels = [];
  bool _loadingModels = false;

  @override
  void initState() {
    super.initState();
    _loadCurrentSettings();
  }

  Future<void> _loadCurrentSettings() async {
    final settings = ref.read(fullSettingsProvider).valueOrNull ?? {};
    _modelController.text = (settings['llm_model'] as String?) ?? '';

    switch (widget.providerId) {
      case 'anthropic':
        final masked = settings['anthropic_api_key'] as String?;
        if (masked != null) _apiKeyController.text = masked;
      case 'openai':
        final masked = settings['openai_api_key'] as String?;
        if (masked != null) _apiKeyController.text = masked;
      case 'copilot':
        final masked = settings['github_token'] as String?;
        if (masked != null) _apiKeyController.text = masked;
      case 'ollama':
      case 'copilot-ollama':
        _baseUrlController.text =
            (settings['ollama_base_url'] as String?) ??
            'http://localhost:11434';
    }
  }

  @override
  void dispose() {
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

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final notifier = ref.read(fullSettingsProvider.notifier);

      final model = _modelController.text.trim();
      final apiKey = _apiKeyController.text.trim();
      final baseUrl = _baseUrlController.text.trim();

      switch (widget.providerId) {
        case 'anthropic':
          await notifier.updateFields(
            anthropicApiKey: apiKey.isNotEmpty ? apiKey : '',
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'openai':
          await notifier.updateFields(
            openaiApiKey: apiKey.isNotEmpty ? apiKey : '',
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'copilot':
          await notifier.updateFields(
            githubToken: apiKey.isNotEmpty ? apiKey : '',
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'ollama':
          await notifier.updateFields(
            ollamaBaseUrl: baseUrl.isNotEmpty
                ? baseUrl
                : 'http://localhost:11434',
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
        case 'copilot-ollama':
          await notifier.updateFields(
            ollamaBaseUrl: baseUrl.isNotEmpty
                ? baseUrl
                : 'http://localhost:11434',
            llmModel: model.isNotEmpty ? model : _defaultModel,
          );
      }

      if (mounted) Navigator.pop(context);
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
      title: Row(
        children: [
          ProviderIcon(providerId: widget.providerId, size: 24),
          const SizedBox(width: 10),
          Text(_title),
        ],
      ),
      content: SizedBox(
        width: 400,
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
              TextField(
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
                    onPressed: () => setState(() => _obscureKey = !_obscureKey),
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (_needsBaseUrl) ...[
              TextField(
                controller: _baseUrlController,
                decoration: const InputDecoration(
                  labelText: 'Ollama Base URL',
                  hintText: 'http://localhost:11434',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
            ],
            TextField(
              controller: _modelController,
              decoration: InputDecoration(
                labelText: 'Model',
                hintText: _defaultModel,
                border: const OutlineInputBorder(),
              ),
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
          ],
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
