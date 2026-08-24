enum FileType {
  pdf('pdf'),
  docx('docx'),
  pptx('pptx'),
  xlsx('xlsx'),
  image('image'),
  video('video'),
  audio('audio'),
  markdown('markdown'),
  other('other');

  const FileType(this.value);
  final String value;

  static FileType fromString(String value) {
    return FileType.values.firstWhere(
      (e) => e.value == value,
      orElse: () => FileType.other,
    );
  }
}

enum FileStatus {
  pending('pending'),
  processing('processing'),
  ready('ready'),
  error('error');

  const FileStatus(this.value);
  final String value;

  static FileStatus fromString(String value) {
    return FileStatus.values.firstWhere(
      (e) => e.value == value,
      orElse: () => FileStatus.pending,
    );
  }
}

class SourceFile {
  const SourceFile({
    required this.id,
    required this.classId,
    required this.originalFilename,
    required this.fileType,
    required this.fileSizeBytes,
    required this.rawPath,
    this.convertedPath,
    required this.status,
    this.errorMessage,
    this.metadataJson,
    required this.createdAt,
    required this.updatedAt,
  });

  factory SourceFile.fromJson(Map<String, dynamic> json) {
    return SourceFile(
      id: json['id'] as String,
      classId: json['class_id'] as String,
      originalFilename: json['original_filename'] as String,
      fileType: FileType.fromString(json['file_type'] as String),
      fileSizeBytes: json['file_size_bytes'] as int,
      rawPath: json['raw_path'] as String,
      convertedPath: json['converted_path'] as String?,
      status: FileStatus.fromString(json['status'] as String),
      errorMessage: json['error_message'] as String?,
      metadataJson: json['metadata_json'] as Map<String, dynamic>?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String id;
  final String classId;
  final String originalFilename;
  final FileType fileType;
  final int fileSizeBytes;
  final String rawPath;
  final String? convertedPath;
  final FileStatus status;
  final String? errorMessage;
  final Map<String, dynamic>? metadataJson;
  final DateTime createdAt;
  final DateTime updatedAt;

  Map<String, dynamic> toJson() => {
    'id': id,
    'class_id': classId,
    'original_filename': originalFilename,
    'file_type': fileType.value,
    'file_size_bytes': fileSizeBytes,
    'raw_path': rawPath,
    'converted_path': convertedPath,
    'status': status.value,
    'error_message': errorMessage,
    'metadata_json': metadataJson,
    'created_at': createdAt.toIso8601String(),
    'updated_at': updatedAt.toIso8601String(),
  };

  SourceFile copyWith({
    FileStatus? status,
    String? errorMessage,
    String? convertedPath,
  }) {
    return SourceFile(
      id: id,
      classId: classId,
      originalFilename: originalFilename,
      fileType: fileType,
      fileSizeBytes: fileSizeBytes,
      rawPath: rawPath,
      convertedPath: convertedPath ?? this.convertedPath,
      status: status ?? this.status,
      errorMessage: errorMessage ?? this.errorMessage,
      metadataJson: metadataJson,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}
