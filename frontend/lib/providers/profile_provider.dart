import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/utils/api_client.dart';

final profileProvider =
    NotifierProvider<ProfileNotifier, ProfileState>(ProfileNotifier.new);

/// Machine-readable blocking codes the diet screen must distinguish.
class SuggestionBlock {
  static const profileIncomplete = 'PROFILE_INCOMPLETE';
  static const clinicianReview = 'CLINICIAN_REVIEW_REQUIRED';

  /// Returned when no clinician-approved ACTIVE safety policy exists —
  /// the app then offers only general, clearly-labeled meal browsing.
  static const needsClinicianReview = 'NEEDS_CLINICIAN_REVIEW';
  static const noSafeSuggestion = 'NO_SAFE_SUGGESTION';
  static const consentRequired = 'CONSENT_REQUIRED';

  /// All clinician-facing blocking codes (route to the same safe state).
  static const clinicianCodes = <String>{clinicianReview, needsClinicianReview};
}

class ProfileState {
  final bool isLoading;

  /// Server-calculated pre-pregnancy BMI (never client-supplied).
  final double? prePregnancyBmi;
  final int? gestationalWeek;
  final int? trimester;
  final String? gestationBasis; // lmp | due_date
  final bool complete;
  final List<String> missingFields;
  final List<String> allergies;
  final String? dietaryPreference;
  final List<String> dislikedIngredients;
  final String? cookingTimePreference;
  final String? budgetPreference;
  final double? heightCm;
  final double? prePregnancyWeightKg;

  /// User-facing message for the last failed operation.
  final String? error;

  const ProfileState({
    this.isLoading = false,
    this.prePregnancyBmi,
    this.gestationalWeek,
    this.trimester,
    this.gestationBasis,
    this.complete = false,
    this.missingFields = const [],
    this.allergies = const [],
    this.dietaryPreference,
    this.dislikedIngredients = const [],
    this.cookingTimePreference,
    this.budgetPreference,
    this.heightCm,
    this.prePregnancyWeightKg,
    this.error,
  });

  ProfileState copyWith({
    bool? isLoading,
    double? prePregnancyBmi,
    int? gestationalWeek,
    int? trimester,
    String? gestationBasis,
    bool? complete,
    List<String>? missingFields,
    List<String>? allergies,
    String? dietaryPreference,
    List<String>? dislikedIngredients,
    String? cookingTimePreference,
    String? budgetPreference,
    double? heightCm,
    double? prePregnancyWeightKg,
    String? error,
  }) {
    return ProfileState(
      isLoading: isLoading ?? this.isLoading,
      prePregnancyBmi: prePregnancyBmi ?? this.prePregnancyBmi,
      gestationalWeek: gestationalWeek ?? this.gestationalWeek,
      trimester: trimester ?? this.trimester,
      gestationBasis: gestationBasis ?? this.gestationBasis,
      complete: complete ?? this.complete,
      missingFields: missingFields ?? this.missingFields,
      allergies: allergies ?? this.allergies,
      dietaryPreference: dietaryPreference ?? this.dietaryPreference,
      dislikedIngredients: dislikedIngredients ?? this.dislikedIngredients,
      cookingTimePreference: cookingTimePreference ?? this.cookingTimePreference,
      budgetPreference: budgetPreference ?? this.budgetPreference,
      heightCm: heightCm ?? this.heightCm,
      prePregnancyWeightKg: prePregnancyWeightKg ?? this.prePregnancyWeightKg,
      error: error,
    );
  }
}

class ProfileNotifier extends Notifier<ProfileState> {
  late final ApiClient _api;

  @override
  ProfileState build() {
    _api = ref.read(apiClientProvider);
    return const ProfileState();
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
    debugPrint('Profile error: $e');
    return fallback;
  }

  /// Load completion status from the server (BMI/week/trimester are
  /// server-calculated; the client only displays them).
  Future<void> loadCompletion() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.get('/api/v1/profile/completion');
      final d = Map<String, dynamic>.from(res.data);
      state = ProfileState(
        isLoading: false,
        prePregnancyBmi: (d['pre_pregnancy_bmi'] as num?)?.toDouble(),
        gestationalWeek: d['gestational_week'] as int?,
        trimester: d['trimester'] as int?,
        gestationBasis: d['gestation_basis'] as String?,
        complete: d['complete'] == true,
        missingFields: List<String>.from(d['missing_fields'] ?? const []),
        allergies: List<String>.from(d['declared_allergies'] ?? const []),
        dietaryPreference: d['dietary_preference'] as String?,
        heightCm: (d['height_cm'] as num?)?.toDouble(),
        prePregnancyWeightKg:
            (d['pre_pregnancy_weight_kg'] as num?)?.toDouble(),
      );
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: _extractError(e, 'Could not load your profile.'),
      );
    }
  }

  /// Save core biometrics/dates (BMI is NOT accepted — server computes it).
  Future<String?> saveCoreProfile({
    required double heightCm,
    required double prePregnancyWeightKg,
    String? lmpDate, // ISO 8601 yyyy-MM-dd
    String? dueDate,
  }) async {
    try {
      final body = <String, dynamic>{
        'height_cm': heightCm,
        'pre_pregnancy_weight_kg': prePregnancyWeightKg,
      };
      if (lmpDate != null) body['lmp_date'] = lmpDate;
      if (dueDate != null) body['due_date'] = dueDate;
      await _api.dio.patch('/api/v1/auth/me', data: body);
      await loadCompletion();
      return null;
    } on DioException catch (e) {
      final err = _extractError(e, 'Could not save your details.');
      state = state.copyWith(error: err);
      return err;
    }
  }

  /// Save allergy codes and suggestion preferences.
  Future<String?> savePreferences({
    List<String>? allergies,
    String? dietaryPreference,
    List<String>? dislikedIngredients,
    String? cookingTimePreference,
    String? budgetPreference,
  }) async {
    try {
      final body = <String, dynamic>{};
      if (allergies != null) body['allergies'] = allergies;
      if (dietaryPreference != null) {
        body['dietary_preference'] = dietaryPreference;
      }
      if (dislikedIngredients != null) {
        body['disliked_ingredients'] = dislikedIngredients;
      }
      if (cookingTimePreference != null) {
        body['cooking_time_preference'] = cookingTimePreference;
      }
      if (budgetPreference != null) body['budget_preference'] = budgetPreference;
      await _api.dio.patch('/api/v1/profile/preferences', data: body);
      await loadCompletion();
      return null;
    } on DioException catch (e) {
      final err = _extractError(e, 'Could not save your preferences.');
      state = state.copyWith(error: err);
      return err;
    }
  }
}

/// Extract the machine-readable blocking_code from a generate failure,
/// so the diet screen can route to the right state.
String? blockingCodeFromError(Object e) {
  if (e is! DioException) return null;
  final data = e.response?.data;
  if (data is Map && data['error'] is Map) {
    final details = data['error']['details'];
    if (details is Map && details['blocking_code'] is String) {
      return details['blocking_code'] as String;
    }
  }
  return null;
}
