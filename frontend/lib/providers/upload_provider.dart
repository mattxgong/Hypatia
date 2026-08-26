import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_client.dart';
import 'class_provider.dart';
import 'file_provider.dart';

enum UploadStatus { idle, uploading, complete, error }

class UploadState {
  const UploadState({
    this.status = UploadStatus.idle,
    this.currentFileName = '',
    this.progress = 0.0,
    this.filesDone = 0,
    this.filesTotal = 0,
    this.errorMessage,
  });

  final UploadStatus status;
  final String currentFileName;
  final double progress;
  final int filesDone;
  final int filesTotal;
  final String? errorMessage;

  UploadState copyWith({
    UploadStatus? status,
    String? currentFileName,
    double? progress,
    int? filesDone,
    int? filesTotal,
    String? errorMessage,
  }) {
    return UploadState(
      status: status ?? this.status,
      currentFileName: currentFileName ?? this.currentFileName,
      progress: progress ?? this.progress,
      filesDone: filesDone ?? this.filesDone,
      filesTotal: filesTotal ?? this.filesTotal,
      errorMessage: errorMessage,
    );
  }
}

class UploadProgressNotifier extends Notifier<UploadState> {
  CancelToken? _cancelToken;
  List<String>? _lastPaths;

  @override
  UploadState build() => const UploadState();

  Future<void> uploadFiles(List<String> paths) async {
    final classId = ref.read(currentClassIdProvider);
    if (classId == null || paths.isEmpty) return;

    _lastPaths = paths;
    _cancelToken = CancelToken();
    final fileNames =
        paths.map((p) => p.split(RegExp(r'[/\\]')).last).toList();

    state = UploadState(
      status: UploadStatus.uploading,
      currentFileName: fileNames.first,
      filesTotal: paths.length,
    );

    final apiClient = ref.read(apiClientProvider);
    try {
      await apiClient.uploadFiles(
        classId,
        paths,
        onProgress: (sent, total) {
          if (total > 0) {
            state = state.copyWith(progress: sent / total);
          }
        },
        cancelToken: _cancelToken,
      );
      state = state.copyWith(
        status: UploadStatus.complete,
        filesDone: paths.length,
        progress: 1.0,
      );
      ref.invalidate(fileListProvider(classId));
    } on DioException catch (e) {
      if (e.type == DioExceptionType.cancel) {
        state = const UploadState();
        return;
      }
      state = state.copyWith(
        status: UploadStatus.error,
        errorMessage: e.message ?? 'Upload failed',
      );
    } on ApiException catch (e) {
      state = state.copyWith(
        status: UploadStatus.error,
        errorMessage: e.detail,
      );
    }
  }

  void cancel() {
    _cancelToken?.cancel();
    _cancelToken = null;
    state = const UploadState();
  }

  void retry() {
    final paths = _lastPaths;
    if (paths != null && paths.isNotEmpty) {
      uploadFiles(paths);
    }
  }

  void reset() {
    state = const UploadState();
  }
}

final uploadProgressProvider =
    NotifierProvider<UploadProgressNotifier, UploadState>(
      UploadProgressNotifier.new,
    );
