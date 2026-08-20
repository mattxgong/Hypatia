import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/source_file.dart';

final fileListProvider = Provider.family<List<SourceFile>, String>((
  ref,
  classId,
) {
  return _mockFiles;
});

final _mockFiles = [
  SourceFile(
    id: 'file-1',
    classId: 'class-1',
    name: 'lecture-1.mp4',
    fileType: FileType.mp4,
    status: FileStatus.ready,
    createdAt: DateTime(2024, 9, 1),
  ),
  SourceFile(
    id: 'file-2',
    classId: 'class-1',
    name: 'chapter-3-notes.pdf',
    fileType: FileType.pdf,
    status: FileStatus.ready,
    createdAt: DateTime(2024, 9, 2),
  ),
  SourceFile(
    id: 'file-3',
    classId: 'class-1',
    name: 'slides-week-2.pptx',
    fileType: FileType.pptx,
    status: FileStatus.processing,
    createdAt: DateTime(2024, 9, 3),
  ),
];
