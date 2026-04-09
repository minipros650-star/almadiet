import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

String _getBaseUrl() {
  // Use the live Render URL for all platforms!
  // NOTE: If your Render URL has extra numbers/letters at the end (e.g. almadiet-api-x7b2.onrender.com),
  // you must update this string exactly!
  return 'https://almadiet.onrender.com';
}

class ApiClient {
  late final Dio _dio;
  String? _token;

  ApiClient() {
    final baseUrl = _getBaseUrl();
    debugPrint('🌐 ApiClient baseUrl: $baseUrl');

    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        if (_token != null) {
          options.headers['Authorization'] = 'Bearer $_token';
        }
        return handler.next(options);
      },
      onError: (error, handler) {
        debugPrint('❌ API Error: ${error.requestOptions.method} ${error.requestOptions.path} → ${error.response?.statusCode} ${error.response?.data}');
        if (error.response?.statusCode == 401) {
          clearToken();
        }
        return handler.next(error);
      },
    ));
  }

  Dio get dio => _dio;

  void setToken(String token) {
    _token = token;
  }

  void clearToken() {
    _token = null;
  }

  bool get isAuthenticated => _token != null;

  Future<void> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('auth_token');
  }

  Future<void> saveToken(String token) async {
    _token = token;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('auth_token', token);
  }

  Future<void> removeToken() async {
    _token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('auth_token');
  }

  /// Update base URL for different platforms
  void setBaseUrl(String url) {
    _dio.options.baseUrl = url;
  }
}

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient();
});

