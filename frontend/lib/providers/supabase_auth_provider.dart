import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/config/app_config.dart';

/// Authentication state driven entirely by Supabase Auth.
///
/// Sessions are persisted by the official SDK (secure storage on
/// Android/iOS, encrypted storage on web) — raw tokens are never written to
/// SharedPreferences by app code.
class SupabaseAuthState {
  final bool isLoading;
  final bool isCheckingSession;
  final bool isAuthenticated;
  final Session? session;
  final User? user;

  /// User-facing message for the last failed operation (never raw errors,
  /// never token material).
  final String? error;

  const SupabaseAuthState({
    this.isLoading = false,
    this.isCheckingSession = false,
    this.isAuthenticated = false,
    this.session,
    this.user,
    this.error,
  });

  SupabaseAuthState copyWith({
    bool? isLoading,
    bool? isCheckingSession,
    bool? isAuthenticated,
    Session? session,
    User? user,
    String? error,
  }) {
    return SupabaseAuthState(
      isLoading: isLoading ?? this.isLoading,
      isCheckingSession: isCheckingSession ?? this.isCheckingSession,
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      session: session ?? this.session,
      user: user ?? this.user,
      error: error,
    );
  }

  String get displayName =>
      user?.userMetadata?['full_name'] as String? ??
      user?.userMetadata?['name'] as String? ??
      user?.email?.split('@').first ??
      '';
}

class SupabaseAuthNotifier extends Notifier<SupabaseAuthState> {
  /// Safe accessor: returns null when Supabase was never initialized
  /// (unit tests, or a build without public configuration) so the provider
  /// degrades to a signed-out state instead of crashing.
  GoTrueClient? get _auth {
    try {
      return Supabase.instance.client.auth;
    } catch (_) {
      return null;
    }
  }

  StreamSubscription<AuthState>? _sub;

  @override
  SupabaseAuthState build() {
    final auth = _auth;
    if (auth == null) {
      return const SupabaseAuthState();
    }
    // React to all auth changes (sign-in, token refresh, sign-out) from the
    // SDK's single source of truth.
    _sub = auth.onAuthStateChange.listen(_onAuthEvent);
    ref.onDispose(() => _sub?.cancel());

    // Restore any persisted session at startup.
    final session = auth.currentSession;
    if (session != null) {
      return SupabaseAuthState(
        isAuthenticated: true,
        session: session,
        user: session.user,
      );
    }
    return const SupabaseAuthState();
  }

  void _onAuthEvent(AuthState event) {
    final session = event.session;
    switch (event.event) {
      case AuthChangeEvent.signedIn:
      case AuthChangeEvent.tokenRefreshed:
      case AuthChangeEvent.initialSession:
        if (session != null) {
          state = SupabaseAuthState(
            isAuthenticated: true,
            session: session,
            user: session.user,
          );
        }
      case AuthChangeEvent.signedOut:
        state = const SupabaseAuthState();
      case AuthChangeEvent.userUpdated:
        if (session != null) {
          state = state.copyWith(session: session, user: session.user);
        }
      default:
        break;
    }
  }

  /// Start Google OAuth via Supabase. On mobile this deep-links back to
  /// com.almadiet.almadiet://login-callback/; on web it uses the browser
  /// redirect. Returns false with a user-facing message on failure.
  Future<bool> signInWithGoogle() async {
    state = state.copyWith(isLoading: true, error: null);
    final auth = _auth;
    if (auth == null) {
      state = state.copyWith(
        isLoading: false,
        error: 'Sign-in is not configured in this build. Please update the app.',
      );
      return false;
    }
    try {
      await auth.signInWithOAuth(
        OAuthProvider.google,
        redirectTo: AppConfig.oauthRedirect,
      );
      // On web the browser navigates away; on mobile the deep link returns
      // and the onAuthStateChange listener flips isAuthenticated.
      state = state.copyWith(isLoading: false);
      return true;
    } on AuthApiException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: _friendlyAuthError(e.message, fallback: 'Google sign-in is unavailable right now. Please try again.'),
      );
      return false;
    } on AuthException {
      state = state.copyWith(
        isLoading: false,
        error: 'Google sign-in could not start. Check your connection and try again.',
      );
      return false;
    } catch (_) {
      state = state.copyWith(
        isLoading: false,
        error: 'Google sign-in could not start. Please try again.',
      );
      return false;
    }
  }

  /// Called when the OAuth deep link returns WITHOUT a session (cancelled
  /// login, denied permission, or invalid redirect).
  void handleOAuthCancelled() {
    if (!state.isAuthenticated) {
      state = state.copyWith(
        isLoading: false,
        error: 'Sign-in was cancelled. You can try again any time.',
      );
    }
  }

  /// Clear a transient error (e.g. after the user dismisses a banner).
  void clearError() {
    state = state.copyWith(error: null);
  }

  /// Logout: revoke the Supabase session, wipe SDK-persisted storage, and
  /// reset in-memory state. Screen-level providers clear their caches.
  Future<void> logout() async {
    try {
      await _auth?.signOut();
    } catch (_) {
      // Local state is cleared regardless; the session will expire
      // server-side if the network call failed.
    }
    state = const SupabaseAuthState();
  }

  /// True when the persisted session is present but can no longer be used
  /// (refresh failed server-side). The SDK drops such sessions itself.
  bool get hasExpiredSession =>
      state.isAuthenticated && _auth?.currentSession == null;

  String _friendlyAuthError(String? message, {required String fallback}) {
    final m = (message ?? '').toLowerCase();
    if (m.contains('cancel') || m.contains('closed by user')) {
      return 'Sign-in was cancelled. You can try again any time.';
    }
    if (m.contains('redirect')) {
      return 'Sign-in redirect failed. Please try again.';
    }
    if (m.contains('network') || m.contains('fetch')) {
      return 'Cannot connect to sign-in. Check your internet connection.';
    }
    return fallback;
  }
}

final supabaseAuthProvider =
    NotifierProvider<SupabaseAuthNotifier, SupabaseAuthState>(
  SupabaseAuthNotifier.new,
);
