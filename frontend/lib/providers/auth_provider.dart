import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/utils/api_client.dart';
import 'supabase_auth_provider.dart';

/// Canonical auth provider name used across screens and the router.
/// (Backwards-compatible alias for the original provider name.)
final authStateProvider =
    NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);

/// Authentication provider — Supabase Auth is the single source of truth.
///
/// The previous custom email/password JWT flow (client-held access+refresh
/// tokens, manual rotation) is RETIRED. The public interface used by
/// screens is preserved (login/register/logout/updateProfile/acceptConsent,
/// AuthState fields) so existing screens keep working, but:
///   * login() delegates to Google OAuth via Supabase (the login screen's
///     email/password form is superseded by "Continue with Google");
///   * register() starts the same Google signup flow;
///   * the backend receives the Supabase access token automatically via
///     the Dio interceptor — no client-held token management remains.
class AuthState {
  final bool isLoading;
  final bool isAuthenticated;
  final bool isCheckingSession;
  final Map<String, dynamic>? user;

  /// User-facing message for the last failed operation (never raw errors).
  final String? error;

  /// Set when the backend rejected the request because onboarding consent
  /// has not been recorded yet — the app must route the user to consent.
  final bool consentRequired;

  /// Set after a refresh attempt failed — the session is over.
  final bool sessionExpired;

  const AuthState({
    this.isLoading = false,
    this.isAuthenticated = false,
    this.isCheckingSession = false,
    this.user,
    this.error,
    this.consentRequired = false,
    this.sessionExpired = false,
  });

  AuthState copyWith({
    bool? isLoading,
    bool? isAuthenticated,
    bool? isCheckingSession,
    Map<String, dynamic>? user,
    String? error,
    bool? consentRequired,
    bool? sessionExpired,
  }) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      isCheckingSession: isCheckingSession ?? this.isCheckingSession,
      user: user ?? this.user,
      // error is nullable-by-default (explicitly clearable).
      error: error,
      consentRequired: consentRequired ?? this.consentRequired,
      sessionExpired: sessionExpired ?? this.sessionExpired,
    );
  }
}

class AuthNotifier extends Notifier<AuthState> {
  ApiClient? _apiInstance;

  ApiClient get _api {
    final existing = _apiInstance;
    if (existing != null) return existing;
    final created = ref.read(apiClientProvider);
    _apiInstance = created;
    return created;
  }

  @override
  AuthState build() {
    _api.onSessionExpired((_) {
      state = const AuthState(sessionExpired: true);
    });

    final sb = ref.watch(supabaseAuthProvider);
    if (sb.isAuthenticated) {
      // Mirror the Supabase session; consent/profile details are fetched
      // lazily by screens that need them.
      _hydrateUserFromSupabase(sb.user);
      return AuthState(
        isAuthenticated: true,
        user: state.user,
      );
    }
    return const AuthState();
  }

  void _hydrateUserFromSupabase(User? sbUser) {
    if (sbUser == null) return;
    state = state.copyWith(
      user: {
        'id': sbUser.id,
        'email': sbUser.email ?? '',
        'name': sbUser.userMetadata?['full_name'] as String? ??
            sbUser.userMetadata?['name'] as String? ??
            '',
      },
    );
  }

  /// Google sign-in via Supabase. Treated as login OR signup — Supabase
  /// creates the account on first authentication and the backend mirrors
  /// the profile on first API call.
  Future<bool> login() => startGoogleSignIn();

  Future<bool> register({String? name}) => startGoogleSignIn();

  Future<bool> startGoogleSignIn() async {
    state = state.copyWith(isLoading: true, error: null);
    final ok = await ref.read(supabaseAuthProvider.notifier).signInWithGoogle();
    final sb = ref.read(supabaseAuthProvider);
    state = state.copyWith(
      isLoading: false,
      error: sb.error,
      isAuthenticated: sb.isAuthenticated,
    );
    if (sb.isAuthenticated) {
      _hydrateUserFromSupabase(sb.user);
      final consentOk = await _refreshConsentFlag();
      state = state.copyWith(consentRequired: !consentOk);
    }
    return ok && sb.isAuthenticated;
  }

  /// Called when an OAuth round-trip returns without a session (cancelled,
  /// denied, invalid redirect). Shows a friendly message; never crashes.
  void handleOAuthCancelled() {
    ref.read(supabaseAuthProvider.notifier).handleOAuthCancelled();
    final sb = ref.read(supabaseAuthProvider);
    state = state.copyWith(
      isLoading: false,
      error: sb.isAuthenticated ? null : 'Sign-in was cancelled. You can try again any time.',
    );
  }

  void clearError() => state = state.copyWith(error: null);

  /// Extract a user-facing message from the backend's error envelope
  /// ({ "error": { code, message, details } }), with safe fallbacks.
  String _extractError(Object e, String fallback) {
    if (e is DioException) {
      final data = e.response?.data;
      if (data is Map && data['error'] is Map) {
        final message = data['error']['message'];
        if (message is String && message.isNotEmpty) return message;
      }
      if (data is Map && data['detail'] is String) {
        return data['detail'] as String;
      }
      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout) {
        return 'Cannot connect to the server. Check your internet connection.';
      }
      if (e.type == DioExceptionType.receiveTimeout) {
        return 'The server took too long to respond. Please try again.';
      }
    }
    return fallback;
  }

  /// Check the backend for current-version consent.
  Future<bool> _refreshConsentFlag() async {
    try {
      final res = await _api.dio.get('/api/v1/consent/current');
      final accepted = res.data['accepted'] == true;
      if (ref.mounted) {
        state = state.copyWith(consentRequired: !accepted);
      }
      return accepted;
    } on DioException {
      // If the status check itself fails, do not block the user on consent —
      // the 409 on submission remains the safety net.
      return true;
    }
  }

  /// Re-check consent status after a 409 CONSENT_REQUIRED from a data
  /// endpoint; used by screens that hit the consent gate.
  Future<void> refreshConsentRequired() => _refreshConsentFlag();

  /// Update the profile via authenticated PATCH and refresh local state from
  /// the confirmed backend response. Returns (success, userFacingError).
  Future<(bool, String?)> updateProfile(Map<String, dynamic> changes) async {
    try {
      final res = await _api.dio.patch('/api/v1/auth/me', data: changes);
      state = state.copyWith(
        isLoading: false,
        error: null,
        user: Map<String, dynamic>.from(res.data),
      );
      return (true, null);
    } on DioException catch (e) {
      return (false, _extractError(e, 'Could not update your profile.'));
    }
  }

  /// Record onboarding consent (required before health data collection).
  Future<bool> acceptConsent(String consentVersion) async {
    try {
      await _api.dio.post(
        '/api/v1/consent',
        data: {'consent_version': consentVersion},
      );
      state = state.copyWith(consentRequired: false);
      return true;
    } on DioException catch (e) {
      final isConflict = e.response?.statusCode == 409;
      state = state.copyWith(
        consentRequired: isConflict ? true : state.consentRequired,
        error: isConflict ? null : _extractError(e, 'Could not record consent.'),
      );
      return false;
    }
  }

  Future<void> logout() async {
    // Supabase sign-out revokes the session and wipes SDK-persisted
    // storage; apiClient clears any remaining local cached state.
    await ref.read(supabaseAuthProvider.notifier).logout();
    await _api.clearLocalSessionState();
    state = const AuthState();
  }
}

/// Whether a Supabase session exists (used by the router's redirect logic).
bool supabaseSessionActive(Ref ref) =>
    ref.watch(supabaseAuthProvider).isAuthenticated;
