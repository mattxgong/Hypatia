enum FileType {
  pdf,
  docx,
  pptx,
  xlsx,
  csv,
  txt,
  md,
  mp4,
  avi,
  mov,
  mkv,
  mp3,
  wav,
  m4a,
  png,
  jpg,
  gif,
}

enum FileStatus { pending, processing, ready, error }

class SourceFile {
  const SourceFile({
    required this.id,
    required this.classId,
    required this.name,
    required this.fileType,
    required this.status,
    required this.createdAt,
  });

  final String id;
  final String classId;
  final String name;
  final FileType fileType;
  final FileStatus status;
  final DateTime createdAt;
}
