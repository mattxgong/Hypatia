import 'package:flutter/material.dart';

import '../../services/api_client.dart';

class ErrorCard extends StatelessWidget {
  const ErrorCard({
    super.key,
    required this.error,
    this.onRetry,
    this.compact = false,
  });

  final Object error;
  final VoidCallback? onRetry;
  final bool compact;

  String get _message {
    if (error is ApiException) return (error as ApiException).detail;
    return error.toString();
  }

  String? get _userAction {
    if (error is ApiException) return (error as ApiException).userAction;
    return null;
  }

  String? get _code {
    if (error is ApiException) return (error as ApiException).code;
    return null;
  }

  IconData get _icon {
    final code = _code;
    if (code == null) return Icons.error_outline;
    if (code.startsWith('LLM_')) return Icons.cloud_off;
    if (code == 'NOT_FOUND') return Icons.search_off;
    if (code == 'FILE_TOO_LARGE') return Icons.file_present;
    if (code == 'FFMPEG_NOT_FOUND') return Icons.videocam_off;
    return Icons.error_outline;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    if (compact) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_icon, size: 16, color: colorScheme.error),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              _message,
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.error,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (onRetry != null) ...[
            const SizedBox(width: 8),
            IconButton(
              icon: const Icon(Icons.refresh, size: 16),
              onPressed: onRetry,
              tooltip: 'Retry',
              visualDensity: VisualDensity.compact,
            ),
          ],
        ],
      );
    }

    return Card(
      color: colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(_icon, color: colorScheme.onErrorContainer),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _message,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: colorScheme.onErrorContainer,
                    ),
                  ),
                ),
              ],
            ),
            if (_userAction != null) ...[
              const SizedBox(height: 8),
              Text(
                _userAction!,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: colorScheme.onErrorContainer.withValues(alpha: 0.8),
                ),
              ),
            ],
            if (onRetry != null) ...[
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerRight,
                child: FilledButton.tonalIcon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Retry'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
