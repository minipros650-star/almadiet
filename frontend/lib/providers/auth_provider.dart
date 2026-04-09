import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/utils/api_client.dart';

final authStateProvider = NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);

class AuthState {
  final bool isLoading;
  final bool isAuthenticated;
  final Map<String, dynamic>? user;
  final String? error;

  const AuthState({this.isLoading = false, this.isAuthenticated = false, this.user, this.error});

  AuthState copyWith({bool? isLoading, bool? isAuthenticated, Map<String, dynamic>? user, String? error}) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      user: user ?? this.user,
      error: error,
    );
  }
}

class AuthNotifier extends Notifier<AuthState> {
  late final ApiClient _api;

  @override
  AuthState build() {
    _api = ref.read(apiClientProvider);
    _checkAuth();
    return const AuthState();
  }

  Future<void> _checkAuth() async {
    await _api.loadToken();
    if (_api.isAuthenticated) {
      try {
        final res = await _api.dio.get('/api/auth/me');
        state = AuthState(isAuthenticated: true, user: res.data);
      } catch (_) {
        await _api.removeToken();
      }
    }
  }

  String _extractError(dynamic e, String fallback) {
    if (e is DioException) {
      final data = e.response?.data;
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
      if (e.type == DioExceptionType.connectionError || e.type == DioExceptionType.connectionTimeout) {
        return 'Cannot connect to server. Is the backend running?';
      }
    }
    debugPrint('Auth error: $e');
    return fallback;
  }

  Future<bool> login(String email, String password) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final res = await _api.dio.post('/api/auth/login', data: {'email': email, 'password': password});
      await _api.saveToken(res.data['access_token']);
      state = AuthState(isAuthenticated: true, user: res.data['user']);
      return true;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: _extractError(e, 'Invalid email or password'));
      return false;
    }
  }

  Future<bool> register({
    required String email, required String password, required String name,
    String region = 'kerala', String language = 'en', int? age,
  }) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final body = <String, dynamic>{
        'email': email,
        'password': password,
        'name': name,
        'region': region,
        'language': language,
      };
      if (age != null) body['age'] = age;

      debugPrint('📤 Register request: $body');
      final res = await _api.dio.post('/api/auth/register', data: body);
      debugPrint('📥 Register response: ${res.data}');

      await _api.saveToken(res.data['access_token']);
      state = AuthState(isAuthenticated: true, user: res.data['user']);
      return true;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: _extractError(e, 'Registration failed'));
      return false;
    }
  }

  Future<void> logout() async {
    await _api.removeToken();
    state = const AuthState();
  }
}

