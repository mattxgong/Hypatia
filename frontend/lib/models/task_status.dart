class TaskStatus {
  const TaskStatus({
    required this.taskId,
    required this.operation,
    required this.classId,
    required this.status,
    this.progress = 0,
    this.message = '',
    this.error,
    required this.createdAt,
  });

  factory TaskStatus.fromJson(Map<String, dynamic> json) {
    return TaskStatus(
      taskId: json['task_id'] as String,
      operation: json['operation'] as String,
      classId: json['class_id'] as String,
      status: json['status'] as String,
      progress: (json['progress'] as int?) ?? 0,
      message: (json['message'] as String?) ?? '',
      error: json['error'] as String?,
      createdAt: json['created_at'] as String,
    );
  }

  final String taskId;
  final String operation;
  final String classId;
  final String status;
  final int progress;
  final String message;
  final String? error;
  final String createdAt;

  bool get isActive => status == 'running';
}
