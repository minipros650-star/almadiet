import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/utils/api_client.dart';

final healthProvider = NotifierProvider<HealthNotifier, HealthState>(HealthNotifier.new);

class HealthState {
  final bool isLoading;
  final List<Map<String, dynamic>> records;
  final Map<String, dynamic>? latestRecord;
  final Map<String, dynamic>? analysis;
  final String? error;

  const HealthState({this.isLoading = false, this.records = const [], this.latestRecord, this.analysis, this.error});

  HealthState copyWith({bool? isLoading, List<Map<String, dynamic>>? records, Map<String, dynamic>? latestRecord, Map<String, dynamic>? analysis, String? error}) {
    return HealthState(isLoading: isLoading ?? this.isLoading, records: records ?? this.records, latestRecord: latestRecord ?? this.latestRecord, analysis: analysis ?? this.analysis, error: error);
  }
}

class HealthNotifier extends Notifier<HealthState> {
  late final ApiClient _api;

  @override
  HealthState build() {
    _api = ref.read(apiClientProvider);
    return const HealthState();
  }

  Future<void> loadRecords() async {
    state = state.copyWith(isLoading: true);
    try {
      final res = await _api.dio.get('/api/health/records');
      final records = List<Map<String, dynamic>>.from(res.data);
      state = state.copyWith(isLoading: false, records: records, latestRecord: records.isNotEmpty ? records.first : null);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<String?> submitRecord(Map<String, dynamic> data) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.post('/api/health/record', data: data);
      final record = Map<String, dynamic>.from(res.data);
      state = state.copyWith(isLoading: false, latestRecord: record, records: [record, ...state.records]);
      return record['id'];
    } catch (e) {
      state = state.copyWith(isLoading: false, error: 'Failed to submit');
      return null;
    }
  }

  Future<void> analyzeRecord(String recordId) async {
    try {
      final res = await _api.dio.get('/api/health/analyze/$recordId');
      state = state.copyWith(analysis: Map<String, dynamic>.from(res.data));
    } catch (_) {}
  }
}
