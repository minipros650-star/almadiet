import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../config/app_config.dart';

/// Backend base URL comes from build-time public configuration
/// (--dart-define-from-file=env.local.json). There is no hard-coded
/// development/Render/hosted fallback: missing configuration is a startup
/// error (see AppConfig.ensureConfigured).
///
/// Every protected request carries the current Supabase access token as
/// `Authorization: Bearer <token>`; FastAPI derives the user identity from
/// that token server-side. No user id is ever sent in a body as proof of
/// identity.
///
/// 401 handling: try one silent Supabase session refresh, retry once; if
/// refresh fails, fire the session-expired callback (sign-out + login
/// screen). Never retries indefinitely.
class ApiClient {
  late final Dio _dio;
  bool _refreshing = false;
  final List<void Function(String?)> _sessionListeners = [];

  /// Session accessors. Defaults read the official Supabase SDK session
  /// (secure storage); tests may inject closures. Production never passes
  /// these — behavior is identical.
  final String? Function() _accessTokenProvider;
  final Future<bool> Function() _refreshSessionFn;

  ApiClient({
    String? Function()? accessTokenProvider,
    Future<bool> Function()? refreshSession,
  })  : _accessTokenProvider =
            accessTokenProvider ?? _defaultAccessTokenProvider,
        _refreshSessionFn = refreshSession ?? _defaultRefreshSession {
    _dio = Dio(BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        final token = _currentAccessToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
      onError: (error, handler) async {
        final status = error.response?.statusCode;
        final path = error.requestOptions.path;
        final isAuthEndpoint =
            path.contains('/auth/login') || path.contains('/auth/register');

        if ((status == 401 || status == 403) && !isAuthEndpoint) {
          final retried = error.requestOptions.extra['_retriedAuth'] == true;
          if (!retried && !_refreshing) {
            final refreshed = await _tryRefreshSession();
            if (refreshed) {
              final retryResponse = await _retry(error.requestOptions);
              return handler.resolve(retryResponse);
            }
            // Refresh failed — the session is over.
            _notifySessionExpired();
          } else if (status == 401) {
            _notifySessionExpired();
          }
        }
        return handler.next(error);
      },
    ));
  }

  String? _currentAccessToken() {
    try {
      return _accessTokenProvider();
    } catch (_) {
      return null; // Supabase not initialized (tests) — unauthenticated.
    }
  }

  Future<bool> _tryRefreshSession() async {
    _refreshing = true;
    try {
      return await _refreshSessionFn();
    } catch (_) {
      return false;
    } finally {
      _refreshing = false;
    }
  }


  Dio get dio => _dio;
  String get baseUrl => AppConfig.apiBaseUrl;
  bool get isAuthenticated => _currentAccessToken() != null;

  /// Callbacks fired when the session has expired and cannot be refreshed.
  void onSessionExpired(void Function(String?) listener) {
    _sessionListeners.add(listener);
  }

  void _notifySessionExpired() {
    for (final listener in _sessionListeners) {
      listener(null);
    }
  }

  Future<Response<dynamic>> _retry(RequestOptions requestOptions) async {
    // Re-fetch the SAME RequestOptions with the flag set, so the retried
    // request can never re-enter the refresh path: a retry that still fails
    // 401/403 goes straight to sign-out (no infinite retry loop).
    requestOptions.extra['_retriedAuth'] = true;
    final token = _currentAccessToken();
    if (token != null) {
      requestOptions.headers['Authorization'] = 'Bearer $token';
    }
    return _dio.fetch<dynamic>(requestOptions);
  }

  /// Clear local cached state on logout/session expiry. The Supabase SDK
  /// owns session persistence — nothing token-shaped is stored here.
  Future<void> clearLocalSessionState() async {
    try {
      await Supabase.instance.client.auth.signOut();
    } catch (_) {
      // Proceed with local cleanup regardless.
    }
  }
}

/// Default access-token source: the official Supabase SDK session
/// (secure storage). App code never touches raw token persistence.
String? _defaultAccessTokenProvider() {
  try {
    return Supabase.instance.client.auth.currentSession?.accessToken;
  } catch (_) {
    return null; // Supabase not initialized — unauthenticated.
  }
}

Future<bool> _defaultRefreshSession() async {
  try {
    await Supabase.instance.client.auth.refreshSession();
    return Supabase.instance.client.auth.currentSession != null;
  } catch (_) {
    return false;
  }
}

/// The old custom token storage is intentionally GONE: Supabase manages
/// session persistence via the official SDK (secure storage), satisfying
/// the "no raw tokens in SharedPreferences / custom JWT storage" rule.
final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient();
});
