import 'package:flutter/foundation.dart';

/// AlmaDiet — Public app configuration.
///
/// ONLY public values live here: the Supabase project URL, the Supabase
/// anon/public key, and the FastAPI base URL (Vercel deployment).
/// Secrets (service-role key, JWT secret, database URL, OAuth client
/// secrets) must NEVER be added to the Flutter app — they belong to the
/// backend environment only.
///
/// Values are injected at build time via --dart-define, e.g.:
///   flutter run --dart-define-from-file=env.local.json
/// or individually:
///   flutter run --dart-define=SUPABASE_URL=... --dart-define=SUPABASE_ANON_KEY=...
///
/// The base URLs are stored WITHOUT trailing slashes; accessors normalize
/// joins so callers never worry about double or missing slashes.
class AppConfig {
  static const String _supabaseUrl = String.fromEnvironment('SUPABASE_URL');
  static const String _supabasePublishableKey =
      String.fromEnvironment('SUPABASE_PUBLISHABLE_KEY');
  // Legacy anon/public key name — accepted as a documented compatibility
  // fallback for existing build pipelines.
  static const String _supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');
  static const String _apiBaseUrl = String.fromEnvironment('API_BASE_URL');

  /// The Supabase public key: prefers the current publishable key
  /// (``sb_publishable_…``), falls back to the legacy anon JWT key.
  static String get supabaseKey =>
      _supabasePublishableKey.isNotEmpty ? _supabasePublishableKey : _supabaseAnonKey;

  /// True when compile-time public configuration is present and plausible.
  static bool get isConfigured {
    return _isValidUrl(_supabaseUrl) &&
        _isValidSupabaseKey(supabaseKey) &&
        _isValidUrl(_apiBaseUrl);
  }

  /// Missing/malformed public values (for the developer-safe startup error).
  static List<String> get configurationProblems {
    final problems = <String>[];
    if (!_isValidUrl(_supabaseUrl)) {
      problems.add('SUPABASE_URL is missing or not an https:// URL');
    }
    if (!_isValidSupabaseKey(supabaseKey)) {
      problems.add(
          'SUPABASE_PUBLISHABLE_KEY (or legacy SUPABASE_ANON_KEY) is missing or malformed');
    }
    if (!_isValidUrl(_apiBaseUrl)) {
      problems.add('API_BASE_URL is missing or not an https:// URL');
    }
    return problems;
  }

  /// Supabase project URL, no trailing slash.
  static String get supabaseUrl => _stripTrailingSlash(_supabaseUrl);

  /// Supabase public key (publishable preferred, anon legacy fallback).
  static String get supabasePublicKey => supabaseKey;

  /// FastAPI (Vercel) base URL, no trailing slash.
  static String get apiBaseUrl => _stripTrailingSlash(_apiBaseUrl);

  /// Join a path onto the API base URL regardless of leading/trailing slashes.
  static String apiUrl(String path) {
    final p = path.startsWith('/') ? path : '/$path';
    return '$apiBaseUrl$p';
  }

  /// Deep-link redirect for OAuth callbacks (Android app-links + iOS custom
  /// scheme). Must match the intent filter in AndroidManifest.xml and the
  /// redirect allowlist in the Supabase dashboard.
  static const String oauthRedirect = 'com.almadiet.almadiet://login-callback/';

  /// Fail fast at startup with a developer-safe message when the public
  /// configuration was not injected. Never prints key material.
  static void ensureConfigured() {
    if (kDebugMode && !isConfigured) {
      throw StateError(
        'AlmaDiet is missing public build configuration.\n'
        'Provide values with --dart-define (or --dart-define-from-file):\n'
        '${configurationProblems.map((p) => '  - $p').join('\n')}\n'
        'See frontend/.env.example for the required public keys.',
      );
    }
  }

  static bool _isValidUrl(String v) {
    final u = Uri.tryParse(v);
    return u != null && (u.scheme == 'https' || u.scheme == 'http') && u.host.isNotEmpty;
  }

  static bool _isValidSupabaseKey(String v) {
    if (v.isEmpty) return false;
    if (v.startsWith('sb_publishable_')) return v.length > 15;
    return v.length > 40; // legacy anon JWT form
  }

  static String _stripTrailingSlash(String v) =>
      v.endsWith('/') ? v.substring(0, v.length - 1) : v;
}
