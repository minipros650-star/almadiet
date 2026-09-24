import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/utils/api_client.dart';
import '../core/utils/consent_gate.dart';

/// Sentinel returned by [HealthNotifier.createRecord] when the backend
/// rejected the write because onboarding consent is missing.
const kConsentRequired = 'CONSENT_REQUIRED';

final healthProvider =
    NotifierProvider<HealthNotifier, HealthState>(HealthNotifier.new);

class HealthState {
  final bool isLoading;
  final String? error;
  final List<Map<String, dynamic>> records;
  final Map<String, dynamic>? analysis;

  /// Safety guidance returned by the backend (clinician pathway).
  final List<String> safetyAlerts;

  const HealthState({
    this.isLoading = false,
    this.error,
    this.records = const [],
    this.analysis,
    this.safetyAlerts = const [],
  });

  HealthState copyWith({
    bool? isLoading,
    String? error,
    List<Map<String, dynamic>>? records,
    Map<String, dynamic>? analysis,
    List<String>? safetyAlerts,
  }) {
    return HealthState(
      isLoading: isLoading ?? this.isLoading,
      error: error,
      records: records ?? this.records,
      analysis: analysis,
      safetyAlerts: safetyAlerts ?? this.safetyAlerts,
    );
  }

  /// Most recently created record (newest-first ordering from the API).
  Map<String, dynamic>? get latestRecord =>
      records.isNotEmpty ? records.first : null;
}

class HealthNotifier extends Notifier<HealthState> {
  late final ApiClient _api;

  @override
  HealthState build() {
    _api = ref.read(apiClientProvider);
    return const HealthState();
  }

  String _extractError(Object e, String fallback) {
    if (e is DioException) {
      final data = e.response?.data;
      if (data is Map && data['error'] is Map) {
        final message = data['error']['message'];
        if (message is String && message.isNotEmpty) return message;
      }
      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout) {
        return 'Cannot connect to the server. Check your internet connection.';
      }
    }
    debugPrint('Health error: $e');
    return fallback;
  }

  Future<void> loadRecords() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.get('/api/v1/health/records');
      state = state.copyWith(
        isLoading: false,
        records: List<Map<String, dynamic>>.from(res.data),
      );
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: _extractError(e, 'Could not load your health information.'),
      );
    }
  }

  /// Create a health record. Returns error message or null on success;
  /// returns [kConsentRequired] when the write was rejected by the consent
  /// gate (409) so screens can route to the consent flow.
  Future<String?> createRecord(Map<String, dynamic> data) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.post('/api/v1/health/record', data: data);
      state = state.copyWith(
        isLoading: false,
        records: [
          Map<String, dynamic>.from(res.data),
          ...state.records,
        ],
      );
      return null;
    } on DioException catch (e) {
      if (isConsentRequiredError(e)) {
        state = state.copyWith(isLoading: false);
        return kConsentRequired;
      }
      final err = _extractError(e, 'Could not save your health information.');
      state = state.copyWith(isLoading: false, error: err);
      return err;
    }
  }

  /// Fetch the non-diagnostic information summary for a record.
  Future<void> loadAnalysis(int recordId) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.get('/api/v1/health/records/$recordId');
      final data = Map<String, dynamic>.from(res.data);
      state = state.copyWith(
        isLoading: false,
        analysis: data,
        safetyAlerts: List<String>.from(data['safety_alerts'] ?? const []),
      );
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: _extractError(e, 'Could not load the summary.'),
      );
    }
  }
}
