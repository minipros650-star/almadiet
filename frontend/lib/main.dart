import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

/// The single app entry point.
///
/// `bootstrap()` (in app.dart) MUST run before `runApp`: it validates the
/// public build configuration and calls `Supabase.initialize(...)`. Skipping
/// it does not crash the app — the auth provider degrades to a signed-out
/// state and sign-in buttons report "not configured", which is exactly the
/// silent failure this ordering bug caused.
Future<void> main() async {
  try {
    await bootstrap();
  } catch (e) {
    // A release build still opens (degraded, signed out) on a bootstrap
    // failure; debug builds rethrow so the developer sees it immediately.
    if (kDebugMode) rethrow;
  }
  runApp(const ProviderScope(child: AlmaDietApp()));
}
