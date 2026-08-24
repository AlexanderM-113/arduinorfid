import 'package:flutter/material.dart';
import '../appwrite_service.dart';
import 'package:appwrite/models.dart' as models;

class CloneDetectionPage extends StatefulWidget {
  const CloneDetectionPage({super.key});

  @override
  State<CloneDetectionPage> createState() => _CloneDetectionPageState();
}

class _CloneDetectionPageState extends State<CloneDetectionPage> {
  late Future<List<models.Document>> cloneRecords;

  @override
  void initState() {
    super.initState();
    cloneRecords = AppwriteService().getCloneRecords();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🚨 Clone Detection'),
        elevation: 0,
        centerTitle: true,
      ),
      body: FutureBuilder<List<models.Document>>(
        future: cloneRecords,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (!snapshot.hasData || snapshot.data!.isEmpty) {
            return const Center(
              child: Text('No cloning attempts detected.'),
            );
          }

          final records = snapshot.data!;
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: records.length,
            itemBuilder: (context, index) {
              final record = records[index];
              return Card(
                color: Colors.red.withOpacity(0.1),
                child: ListTile(
                  leading: const Icon(Icons.warning, color: Colors.red),
                  title: Text(
                    'Clone Detected',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Original: ${record.data['original_uid']}'),
                      Text('Cloned: ${record.data['cloned_uid']}'),
                      Text('Time: ${record.data['timestamp']}'),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
