import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/chat_message.dart';
import '../models/source_file.dart';
import '../models/wiki_page.dart';
import '../models/hypatia_class.dart';

final backendBaseUrlProvider = StateProvider<String>(
  (ref) => 'http://127.0.0.1:8000',
);

final apiClientProvider = Provider<ApiClient>((ref) {
  final baseUrl = ref.watch(backendBaseUrlProvider);
  return ApiClient(baseUrl: baseUrl);
});

class ApiException implements Exception {
  ApiException({required this.detail, this.code, this.statusCode});

  final String detail;
  final String? code;
  final int? statusCode;

  @override
  String toString() => 'ApiException($statusCode): $detail';
}

class ApiClient {
  ApiClient({required String baseUrl})
    : _dio = Dio(
        BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 30),
        ),
      );

  final Dio _dio;

  Never _handleError(DioException e) {
    if (e.response?.data is Map<String, dynamic>) {
      final data = e.response!.data as Map<String, dynamic>;
      throw ApiException(
        detail: data['detail'] as String? ?? e.message ?? 'Unknown error',
        code: data['code'] as String?,
        statusCode: e.response?.statusCode,
      );
    }
    throw ApiException(
      detail: e.message ?? 'Network error',
      statusCode: e.response?.statusCode,
    );
  }

  // --- Classes ---

  Future<List<HypatiaClass>> listClasses() async {
    try {
      final response = await _dio.get<List<dynamic>>('/api/classes');
      return response.data!
          .map((e) => HypatiaClass.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<HypatiaClass> createClass({
    required String name,
    String? description,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/classes',
        data: {'name': name, 'description': description},
      );
      return HypatiaClass.fromJson(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<HypatiaClass> getClass(String classId) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/api/classes/$classId',
      );
      return HypatiaClass.fromJson(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<HypatiaClass> updateClass(
    String classId, {
    String? name,
    String? description,
  }) async {
    try {
      final response = await _dio.put<Map<String, dynamic>>(
        '/api/classes/$classId',
        data: {'name': name, 'description': description},
      );
      return HypatiaClass.fromJson(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<void> deleteClass(String classId) async {
    try {
      await _dio.delete<void>('/api/classes/$classId');
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  // --- Files ---

  Future<List<SourceFile>> listFiles(String classId) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '/api/classes/$classId/files',
      );
      return response.data!
          .map((e) => SourceFile.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<List<Map<String, dynamic>>> uploadFiles(
    String classId,
    List<String> filePaths, {
    void Function(int sent, int total)? onProgress,
    CancelToken? cancelToken,
  }) async {
    final formData = FormData();
    for (final path in filePaths) {
      formData.files.add(MapEntry('files', await MultipartFile.fromFile(path)));
    }
    try {
      final response = await _dio.post<List<dynamic>>(
        '/api/classes/$classId/files',
        data: formData,
        onSendProgress: onProgress,
        cancelToken: cancelToken,
      );
      return response.data!.cast<Map<String, dynamic>>();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<SourceFile> getFile(String classId, String fileId) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/api/classes/$classId/files/$fileId',
      );
      return SourceFile.fromJson(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<void> deleteFile(String classId, String fileId) async {
    try {
      await _dio.delete<void>('/api/classes/$classId/files/$fileId');
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  String getFileRawUrl(String classId, String fileId) {
    return '${_dio.options.baseUrl}/api/classes/$classId/files/$fileId/raw';
  }

  String getFileConvertedUrl(String classId, String fileId) {
    return '${_dio.options.baseUrl}/api/classes/$classId/files/$fileId/converted';
  }

  Future<Uint8List> getFileRaw(String classId, String fileId) async {
    try {
      final response = await _dio.get<List<int>>(
        '/api/classes/$classId/files/$fileId/raw',
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<String> getFileConverted(String classId, String fileId) async {
    try {
      final response = await _dio.get<String>(
        '/api/classes/$classId/files/$fileId/converted',
        options: Options(responseType: ResponseType.plain),
      );
      return response.data!;
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  // --- Wiki ---

  Future<List<WikiPageSummary>> getWikiTree(String classId) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '/api/classes/$classId/wiki/tree',
      );
      return response.data!
          .map((e) => WikiPageSummary.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<String> getWikiIndex(String classId) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/api/classes/$classId/wiki/index',
      );
      return response.data!['content'] as String;
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<WikiPage> getWikiPage(String classId, String pagePath) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/api/classes/$classId/wiki/pages/$pagePath',
      );
      return WikiPage.fromJson(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<WikiPage> updateWikiPage(
    String classId,
    String pagePath,
    String content,
  ) async {
    try {
      final response = await _dio.put<Map<String, dynamic>>(
        '/api/classes/$classId/wiki/pages/$pagePath',
        data: {'content': content},
      );
      return WikiPage.fromJson(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<List<WikiSearchResult>> searchWiki(
    String classId,
    String query, {
    String? category,
    String mode = 'hybrid',
  }) async {
    try {
      final params = <String, dynamic>{'q': query, 'mode': mode};
      if (category != null) params['category'] = category;
      final response = await _dio.get<Map<String, dynamic>>(
        '/api/classes/$classId/wiki/search',
        queryParameters: params,
      );
      final results = response.data!['results'] as List<dynamic>;
      return results
          .map((e) => WikiSearchResult.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<Uint8List> exportWiki(String classId) async {
    try {
      final response = await _dio.post<List<int>>(
        '/api/classes/$classId/wiki/export',
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(response.data!);
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<Map<String, dynamic>> lintWiki(String classId) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/classes/$classId/wiki/lint',
      );
      return response.data!;
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<Map<String, dynamic>> rebuildWiki(
    String classId, {
    bool confirm = false,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/classes/$classId/wiki/rebuild',
        queryParameters: {'confirm': confirm},
      );
      return response.data!;
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  // --- Chat ---

  Future<List<ChatMessage>> getChatHistory(
    String classId, {
    int limit = 50,
    int offset = 0,
  }) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '/api/classes/$classId/chat/history',
        queryParameters: {'limit': limit, 'offset': offset},
      );
      return response.data!
          .map((e) => ChatMessage.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<void> clearChatHistory(String classId) async {
    try {
      await _dio.delete<void>('/api/classes/$classId/chat/history');
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  // --- Tasks ---

  Future<List<Map<String, dynamic>>> listTasks() async {
    try {
      final response = await _dio.get<List<dynamic>>('/api/tasks');
      return response.data!.cast<Map<String, dynamic>>();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<Map<String, dynamic>> getTask(String taskId) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/api/tasks/$taskId',
      );
      return response.data!;
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<void> cancelTask(String taskId) async {
    try {
      await _dio.post<void>('/api/tasks/$taskId/cancel');
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  // --- Settings ---

  Future<Map<String, dynamic>> getSettings() async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/api/settings');
      return response.data!;
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<Map<String, dynamic>> updateSettings({
    String? llmProvider,
    String? llmModel,
    double? llmTemperature,
    int? llmMaxTokens,
    String? anthropicApiKey,
    String? openaiApiKey,
    String? githubToken,
    String? ollamaBaseUrl,
  }) async {
    try {
      final body = <String, dynamic>{};
      if (llmProvider != null) body['llm_provider'] = llmProvider;
      if (llmModel != null) body['llm_model'] = llmModel;
      if (llmTemperature != null) body['llm_temperature'] = llmTemperature;
      if (llmMaxTokens != null) body['llm_max_tokens'] = llmMaxTokens;
      if (anthropicApiKey != null) body['anthropic_api_key'] = anthropicApiKey;
      if (openaiApiKey != null) body['openai_api_key'] = openaiApiKey;
      if (githubToken != null) body['github_token'] = githubToken;
      if (ollamaBaseUrl != null) body['ollama_base_url'] = ollamaBaseUrl;
      final response = await _dio.put<Map<String, dynamic>>(
        '/api/settings',
        data: body,
      );
      return response.data!;
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  Future<List<String>> getOllamaModels() async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '/api/settings/ollama-models',
      );
      return response.data!.cast<String>();
    } on DioException catch (e) {
      _handleError(e);
    }
  }

  // --- WebSocket URL helper ---

  String getChatWebSocketUrl(String classId) {
    final base = _dio.options.baseUrl
        .replaceFirst('http://', 'ws://')
        .replaceFirst('https://', 'wss://');
    return '$base/api/classes/$classId/chat';
  }
}
