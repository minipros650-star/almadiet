import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/utils/api_client.dart';

final dietProvider = NotifierProvider<DietNotifier, DietState>(DietNotifier.new);

class DietState {
  final bool isLoading;
  final List<Map<String, dynamic>> plans;
  final Map<String, dynamic>? currentPlan;
  final String? error;

  const DietState({this.isLoading = false, this.plans = const [], this.currentPlan, this.error});

  DietState copyWith({bool? isLoading, List<Map<String, dynamic>>? plans, Map<String, dynamic>? currentPlan, String? error}) {
    return DietState(isLoading: isLoading ?? this.isLoading, plans: plans ?? this.plans, currentPlan: currentPlan ?? this.currentPlan, error: error);
  }
}

class DietNotifier extends Notifier<DietState> {
  late final ApiClient _api;

  @override
  DietState build() {
    _api = ref.read(apiClientProvider);
    return const DietState();
  }

  Future<void> loadPlans() async {
    state = state.copyWith(isLoading: true);
    try {
      final res = await _api.dio.get('/api/diet/plans');
      final plans = List<Map<String, dynamic>>.from(res.data);
      state = state.copyWith(isLoading: false, plans: plans, currentPlan: plans.isNotEmpty ? plans.first : null);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<bool> generatePlan(String healthRecordId) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.post('/api/diet/generate', data: {'health_record_id': healthRecordId});
      final plan = Map<String, dynamic>.from(res.data);
      state = state.copyWith(isLoading: false, currentPlan: plan, plans: [plan, ...state.plans]);
      return true;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: 'Failed to generate plan');
      return false;
    }
  }
}

// Meals provider
final mealsProvider = FutureProvider.family<List<Map<String, dynamic>>, Map<String, String?>>((ref, filters) async {
  final api = ref.read(apiClientProvider);
  final queryParams = <String, dynamic>{};
  filters.forEach((key, value) {
    if (value != null) queryParams[key] = value;
  });
  final res = await api.dio.get('/api/meals', queryParameters: queryParams);
  return List<Map<String, dynamic>>.from(res.data);
});
