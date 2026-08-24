import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/hypatia_class.dart';
import '../services/api_client.dart';

final classListProvider =
    AsyncNotifierProvider<ClassListNotifier, List<HypatiaClass>>(
      ClassListNotifier.new,
    );

final currentClassIdProvider = StateProvider<String?>((ref) => null);

final currentClassProvider = Provider<HypatiaClass?>((ref) {
  final classId = ref.watch(currentClassIdProvider);
  if (classId == null) return null;
  final classesAsync = ref.watch(classListProvider);
  return classesAsync.valueOrNull?.where((c) => c.id == classId).firstOrNull;
});

class ClassListNotifier extends AsyncNotifier<List<HypatiaClass>> {
  @override
  Future<List<HypatiaClass>> build() async {
    final apiClient = ref.read(apiClientProvider);
    return apiClient.listClasses();
  }

  Future<HypatiaClass> create({
    required String name,
    String? description,
  }) async {
    final apiClient = ref.read(apiClientProvider);
    final newClass = await apiClient.createClass(
      name: name,
      description: description,
    );
    ref.invalidateSelf();
    return newClass;
  }

  Future<void> delete(String classId) async {
    final apiClient = ref.read(apiClientProvider);
    await apiClient.deleteClass(classId);
    ref.invalidateSelf();
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
  }
}
