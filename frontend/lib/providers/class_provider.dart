import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/hypatia_class.dart';

final classListProvider =
    NotifierProvider<ClassListNotifier, List<HypatiaClass>>(
      ClassListNotifier.new,
    );

final currentClassIdProvider = StateProvider<String?>((ref) => null);

final currentClassProvider = Provider<HypatiaClass?>((ref) {
  final classId = ref.watch(currentClassIdProvider);
  if (classId == null) return null;
  final classes = ref.watch(classListProvider);
  return classes.where((c) => c.id == classId).firstOrNull;
});

class ClassListNotifier extends Notifier<List<HypatiaClass>> {
  @override
  List<HypatiaClass> build() {
    return _mockClasses;
  }

  void addClass(HypatiaClass newClass) {
    state = [...state, newClass];
  }

  void removeClass(String classId) {
    state = state.where((c) => c.id != classId).toList();
  }
}

final _mockClasses = [
  HypatiaClass(
    id: 'class-1',
    name: 'Machine Learning',
    description: 'CS229 lecture notes and papers',
    fileCount: 5,
    pageCount: 12,
    createdAt: DateTime(2024, 9, 1),
    updatedAt: DateTime(2024, 9, 15),
  ),
  HypatiaClass(
    id: 'class-2',
    name: 'Organic Chemistry',
    description: 'CHEM 301 materials',
    fileCount: 3,
    pageCount: 8,
    createdAt: DateTime(2024, 9, 5),
    updatedAt: DateTime(2024, 9, 10),
  ),
];
