import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/utils/api_client.dart';
import '../core/utils/consent_gate.dart';
import 'profile_provider.dart';

final dietProvider = NotifierProvider<DietNotifier, DietState>(DietNotifier.new);

/// Machine-readable result of a generate attempt.
class GenerateResult {
  final bool ok;
  final String? blockingCode; // SuggestionBlock constants when blocked
  final String? userMessage;
  const GenerateResult({required this.ok, this.blockingCode, this.userMessage});
}

class DietState {
  final bool isLoading;
  final List<Map<String, dynamic>> plans;
  final Map<String, dynamic>? currentPlan;

  /// User-facing message for the last failed operation.
  final String? error;

  /// Blocking code when generation was refused (profile incomplete etc.).
  final String? blockingCode;

  /// Index of the day currently shown in the 7-day plan view.
  final int selectedDayIndex;

  const DietState({
    this.isLoading = false,
    this.plans = const [],
    this.currentPlan,
    this.error,
    this.blockingCode,
    this.selectedDayIndex = 1,
  });

  DietState copyWith({
    bool? isLoading,
    List<Map<String, dynamic>>? plans,
    Map<String, dynamic>? currentPlan,
    String? error,
    String? blockingCode,
    int? selectedDayIndex,
  }) {
    return DietState(
      isLoading: isLoading ?? this.isLoading,
      plans: plans ?? this.plans,
      currentPlan: currentPlan ?? this.currentPlan,
      error: error,
      blockingCode: blockingCode,
      selectedDayIndex: selectedDayIndex ?? this.selectedDayIndex,
    );
  }
}

/// Day index (1..7) within the plan window that corresponds to today's
/// calendar date, derived from plan_start. Null when today is outside the
/// 7-day window (then Day 1 stays selected).
int? todayPlanDayFor(Map<String, dynamic> plan) {
  final start = DateTime.tryParse('${plan['plan_start'] ?? ''}');
  if (start == null) return null;
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final s = DateTime(start.year, start.month, start.day);
  final diff = today.difference(s).inDays;
  if (diff >= 0 && diff <= 6) return diff + 1;
  return null;
}

class DietNotifier extends Notifier<DietState> {
  late final ApiClient _api;

  @override
  DietState build() {
    _api = ref.read(apiClientProvider);
    return const DietState();
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
    debugPrint('Diet error: $e');
    return fallback;
  }

  Future<void> loadPlans() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.get('/api/v1/diet/plans');
      final plans = List<Map<String, dynamic>>.from(res.data);
      state = state.copyWith(
        isLoading: false,
        plans: plans,
        currentPlan: plans.isNotEmpty ? plans.first : null,
        selectedDayIndex: plans.isNotEmpty ? (todayPlanDayFor(plans.first) ?? 1) : 1,
      );
      if (plans.isEmpty) {
        // No plan yet — ask the server for personalized suggestions.
        // Blocking results (profile incomplete, clinician review, no safe
        // suggestion) set state.blockingCode so the screen explains itself.
        await generatePersonalized();
      }
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: _extractError(e, 'Could not load your meal plans.'),
      );
    }
  }

  /// Personalized suggestions from the server-side profile. Returns a
  /// [GenerateResult] whose [GenerateResult.blockingCode] distinguishes
  /// PROFILE_INCOMPLETE / CLINICIAN_REVIEW_REQUIRED / NO_SAFE_SUGGESTION /
  /// CONSENT_REQUIRED so screens can route to the right state.
  Future<GenerateResult> generatePersonalized() async {
    state = state.copyWith(isLoading: true, error: null, blockingCode: null);
    try {
      final res = await _api.dio.post('/api/v1/diet/generate', data: {});
      final plan = Map<String, dynamic>.from(res.data);
      state = state.copyWith(
        isLoading: false,
        currentPlan: plan,
        plans: [plan, ...state.plans],
        selectedDayIndex: todayPlanDayFor(plan) ?? 1,
      );
      return const GenerateResult(ok: true);
    } on DioException catch (e) {
      final code = blockingCodeFromError(e);
      if (code != null) {
        final message = _extractError(
          e,
          'Personalized suggestions are not available right now.',
        );
        state = state.copyWith(isLoading: false, error: message, blockingCode: code);
        return GenerateResult(ok: false, blockingCode: code, userMessage: message);
      }
      if (isConsentRequiredError(e)) {
        state = state.copyWith(
          isLoading: false,
          blockingCode: SuggestionBlock.consentRequired,
        );
        return const GenerateResult(
          ok: false,
          blockingCode: SuggestionBlock.consentRequired,
        );
      }
      final message = _extractError(e, 'Could not create meal suggestions right now.');
      state = state.copyWith(isLoading: false, error: message);
      return GenerateResult(ok: false, userMessage: message);
    }
  }

  Future<bool> generatePlan(String healthRecordId) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.post(
        '/api/v1/diet/generate',
        data: {'health_record_id': healthRecordId},
      );
      final plan = Map<String, dynamic>.from(res.data);
      state = state.copyWith(
        isLoading: false,
        currentPlan: plan,
        plans: [plan, ...state.plans],
        selectedDayIndex: todayPlanDayFor(plan) ?? 1,
      );
      return true;
    } on DioException catch (e) {
      if (isConsentRequiredError(e)) {
        state = state.copyWith(
          isLoading: false,
          blockingCode: SuggestionBlock.consentRequired,
        );
        return false; // screen layer checks consentRequired flag
      }
      // Surface the machine-readable blocking reason (PROFILE_INCOMPLETE,
      // NEEDS_CLINICIAN_REVIEW, NO_SAFE_SUGGESTION) so screens can route
      // the user to the right safe state instead of failing silently.
      final code = blockingCodeFromError(e);
      state = state.copyWith(
        isLoading: false,
        error: _extractError(e, 'Could not create a meal plan right now.'),
        blockingCode: code,
      );
      return false;
    }
  }

  /// Swap one meal card. Re-fetches the plan so the UI reflects the
  /// backend-confirmed state. Returns error message or null on success.
  Future<String?> swapMeal({
    required String planId,
    required int dayIndex,
    required String slot,
    required String currentMealId,
  }) async {
    try {
      final res = await _api.dio.post(
        '/api/v1/diet/plans/$planId/swap',
        data: {
          'day_index': dayIndex,
          'slot': slot,
          'current_meal_id': currentMealId,
        },
      );
      final plan = Map<String, dynamic>.from(res.data);
      state = state.copyWith(
        currentPlan: plan,
        plans: [
          for (final p in state.plans)
            if (p['id'] == plan['id']) plan else p,
        ],
      );
      return null;
    } on DioException catch (e) {
      return _extractError(e, 'No safe alternative was found for this slot.');
    }
  }

  void selectDay(int dayIndex) {
    state = state.copyWith(selectedDayIndex: dayIndex);
  }
}

// Meals catalog provider
final mealsProvider =
    FutureProvider.family<List<Map<String, dynamic>>, Map<String, String?>>(
        (ref, filters) async {
  final api = ref.read(apiClientProvider);
  final queryParams = <String, dynamic>{};
  filters.forEach((key, value) {
    if (value != null) queryParams[key] = value;
  });
  final res = await api.dio.get('/api/v1/meals', queryParameters: queryParams);
  return List<Map<String, dynamic>>.from(res.data);
});
