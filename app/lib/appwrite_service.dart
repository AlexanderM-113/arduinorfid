import 'package:appwrite/appwrite.dart';

class AppwriteService {
  static final AppwriteService _instance = AppwriteService._internal();

  late Client client;
  late Account account;
  late Databases databases;

  static const String PROJECT_ID = 'your-project-id';
  static const String ENDPOINT = 'https://your-appwrite-instance.com/v1';
  static const String DATABASE_ID = 'smart_attendance';

  factory AppwriteService() {
    return _instance;
  }

  AppwriteService._internal() {
    _initialize();
  }

  void _initialize() {
    client = Client()
      .setEndpoint(ENDPOINT)
      .setProject(PROJECT_ID)
      .setSelfSigned(activate: false); // Set to true for self-hosted dev

    account = Account(client);
    databases = Databases(client);
  }

  // ─── AUTH ───────────────────────────────────────────────────────────────
  Future<bool> login(String email, String password) async {
    try {
      await account.createEmailPasswordSession(
        email: email,
        password: password,
      );
      return true;
    } catch (e) {
      print('Login error: $e');
      return false;
    }
  }

  Future<void> logout() async {
    try {
      await account.deleteSession(sessionId: 'current');
    } catch (e) {
      print('Logout error: $e');
    }
  }

  Future<models.User?> getCurrentUser() async {
    try {
      return await account.get();
    } catch (e) {
      print('Get user error: $e');
      return null;
    }
  }

  // ─── STUDENTS ───────────────────────────────────────────────────────────
  Future<models.Document?> getStudentByRFID(String uid) async {
    try {
      final result = await databases.listDocuments(
        databaseId: DATABASE_ID,
        collectionId: 'students',
        queries: [Query.equal('rfid_uid', uid)],
      );
      return result.documents.isNotEmpty ? result.documents.first : null;
    } catch (e) {
      print('Get student error: $e');
      return null;
    }
  }

  Future<List<models.Document>> getAllStudents() async {
    try {
      final result = await databases.listDocuments(
        databaseId: DATABASE_ID,
        collectionId: 'students',
      );
      return result.documents;
    } catch (e) {
      print('Get students error: $e');
      return [];
    }
  }

  Future<String> createStudent({
    required String rfidUid,
    required String name,
    required String rollNo,
    String? classId,
    String? photoUrl,
  }) async {
    try {
      final doc = await databases.createDocument(
        databaseId: DATABASE_ID,
        collectionId: 'students',
        documentId: ID.unique(),
        data: {
          'rfid_uid': rfidUid,
          'name': name,
          'roll_no': rollNo,
          'class_id': classId,
          'photo_url': photoUrl,
          'created_at': DateTime.now().toIso8601String(),
        },
      );
      return doc.$id;
    } catch (e) {
      print('Create student error: $e');
      rethrow;
    }
  }

  // ─── ATTENDANCE ──────────────────────────────────────────────────────────
  Future<String> logAttendance({
    required String rfidUid,
    required String? studentId,
    required String? studentName,
    String? classId,
  }) async {
    try {
      final now = DateTime.now();
      final doc = await databases.createDocument(
        databaseId: DATABASE_ID,
        collectionId: 'attendance_logs',
        documentId: ID.unique(),
        data: {
          'rfid_uid': rfidUid,
          'student_id': studentId,
          'student_name': studentName ?? 'Unknown',
          'timestamp': now.toIso8601String(),
          'date': now.toString().split(' ')[0], // YYYY-MM-DD
          'time': '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}:${now.second.toString().padLeft(2, '0')}',
          'status': 'present',
          'valid': studentId != null,
          'class_id': classId,
        },
      );
      return doc.$id;
    } catch (e) {
      print('Log attendance error: $e');
      rethrow;
    }
  }

  Stream<RealtimeMessage> getAttendanceStream() {
    return client.subscribe([
      'databases.$DATABASE_ID.collections.attendance_logs.documents'
    ]);
  }

  Future<List<models.Document>> getAttendanceByDate(String date) async {
    try {
      final result = await databases.listDocuments(
        databaseId: DATABASE_ID,
        collectionId: 'attendance_logs',
        queries: [Query.equal('date', date)],
      );
      return result.documents;
    } catch (e) {
      print('Get attendance error: $e');
      return [];
    }
  }

  // ─── RFID CLONER ────────────────────────────────────────────────────────
  Future<String> logCloneAttempt({
    required String originalUid,
    required String clonedUid,
    String? clonedByStudentId,
    String? notes,
    String detectionMethod = 'duplicate_scan',
  }) async {
    try {
      final doc = await databases.createDocument(
        databaseId: DATABASE_ID,
        collectionId: 'rfid_clone_records',
        documentId: ID.unique(),
        data: {
          'original_uid': originalUid,
          'cloned_uid': clonedUid,
          'cloned_by_student_id': clonedByStudentId,
          'timestamp': DateTime.now().toIso8601String(),
          'status': 'success',
          'notes': notes,
          'detection_method': detectionMethod,
        },
      );
      print('🚨 Clone detected and logged: $originalUid -> $clonedUid');
      return doc.$id;
    } catch (e) {
      print('Log clone error: $e');
      rethrow;
    }
  }

  Future<List<models.Document>> getCloneRecords() async {
    try {
      final result = await databases.listDocuments(
        databaseId: DATABASE_ID,
        collectionId: 'rfid_clone_records',
        queries: [Query.orderDesc('timestamp')],
      );
      return result.documents;
    } catch (e) {
      print('Get clone records error: $e');
      return [];
    }
  }

  // ─── CLASSES ────────────────────────────────────────────────────────────
  Future<List<models.Document>> getAllClasses() async {
    try {
      final result = await databases.listDocuments(
        databaseId: DATABASE_ID,
        collectionId: 'classes',
      );
      return result.documents;
    } catch (e) {
      print('Get classes error: $e');
      return [];
    }
  }
}
