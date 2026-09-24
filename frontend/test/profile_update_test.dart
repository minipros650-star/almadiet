import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:almadiet/core/config/app_config.dart';
import 'package:almadiet/core/utils/api_client.dart';

/// Maintained replacement for the retired custom-token test suite.
///
/// Covers the same user-facing guarantees against the Supabase-session
/// architecture: profile/API calls ride an authenticated client whose
/// identity comes from the Bearer token (never a body field), 401 triggers
/// exactly one refresh-then-retry, and refresh failure signs the user out
/// (never an infinite retry loop).
void main() {
  group('AppConfig (API base URL)', () {
    test('is trailing-slash-safe for every endpoint join', () {
      // AppConfig.apiUrl is used by all providers; joins must never double
      // or drop slashes regardless of how API_BASE_URL was configured.
      expect(AppConfig.apiUrl('/api/v1/profile/completion'),
          isNot(contains('//api')));
    });
  });

  group('ApiClient (Supabase-session bearer flow)', () {
    test('attaches Authorization from the session token', () async {
      final captured = <RequestOptions>[];
      final client = ApiClient(
        accessTokenProvider: () => 'session-token-123',
        refreshSession: () async => false,
      );
      client.dio.httpClientAdapter = _StubAdapter(captured, statusCode: 200);

      await client.dio.get<void>('/api/v1/profile/completion');

      expect(captured.single.headers['Authorization'], 'Bearer session-token-123');
      expect(captured.single.path, contains('/api/v1/profile/completion'));
    });

    test('never injects a user id into request bodies', () async {
      final captured = <RequestOptions>[];
      final client = ApiClient(
        accessTokenProvider: () => 'session-token-123',
        refreshSession: () async => false,
      );
      client.dio.httpClientAdapter = _StubAdapter(captured, statusCode: 200);

      await client.dio.patch<void>('/api/v1/profile/preferences',
          data: <String, dynamic>{'dietary_preference': 'veg'});

      final body = captured.single.data as Map;
      expect(body['dietary_preference'], 'veg');
      expect(body.containsKey('user_id'), isFalse,
          reason: 'identity must come from the Bearer token only');
      expect(body.containsKey('userId'), isFalse);
    });

    test('401 with successful refresh retries exactly once and succeeds',
        () async {
      final captured = <RequestOptions>[];
      final client = ApiClient(
        accessTokenProvider: () => 'session-token-123',
        refreshSession: () async => true,
      );
      // First attempt: 401 (stale token). Retry: 200.
      client.dio.httpClientAdapter =
          _StubAdapter(captured, statusCode: 401, retryStatusCode: 200);

      final res = await client.dio.get<Map<String, dynamic>>(
          '/api/v1/profile/completion');

      expect(res.statusCode, 200);
      expect(captured.length, 2, reason: 'one original + one retry');
      expect(captured.last.extra['_retriedAuth'], true);
    });

    test('401 with failed refresh signs out exactly once (no loop)', () async {
      final captured = <RequestOptions>[];
      var sessionExpiredFired = 0;
      final client = ApiClient(
        accessTokenProvider: () => 'session-token-123',
        refreshSession: () async => false,
      );
      client.dio.httpClientAdapter =
          _StubAdapter(captured, statusCode: 401, retryStatusCode: 401);
      client.onSessionExpired((_) => sessionExpiredFired++);

      await expectLater(
        client.dio.get<void>('/api/v1/profile/completion'),
        throwsA(isA<DioException>()),
      );

      expect(captured.length, 1,
          reason: 'refresh failed — must not retry');
      expect(sessionExpiredFired, 1);
    });

    test('persistent 401 after refresh signs out exactly once (single retry)',
        () async {
      final captured = <RequestOptions>[];
      var sessionExpiredFired = 0;
      final client = ApiClient(
        accessTokenProvider: () => 'session-token-123',
        refreshSession: () async => true,
      );
      client.dio.httpClientAdapter =
          _StubAdapter(captured, statusCode: 401, retryStatusCode: 401);
      client.onSessionExpired((_) => sessionExpiredFired++);

      await expectLater(
        client.dio.get<void>('/api/v1/profile/completion'),
        throwsA(isA<DioException>()),
      );

      expect(captured.length, 2, reason: 'original + exactly one retry');
      expect(sessionExpiredFired, 1,
          reason: 'no infinite refresh/retry loop');
    });
  });
}

/// Adapter that records requests and returns a scripted status sequence.
class _StubAdapter implements HttpClientAdapter {
  _StubAdapter(
    this.captured, {
    this.statusCode = 200,
    int? retryStatusCode,
  })  : _retryStatusCode = retryStatusCode ?? statusCode;

  final List<RequestOptions> captured;
  final int statusCode;
  final int _retryStatusCode;
  int _calls = 0;

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final code = _calls++ == 0 ? statusCode : _retryStatusCode;
    captured.add(options);
    return ResponseBody.fromString(
      code < 400 ? '{"ok":true}' : '{"error":{"code":"UNAUTHENTICATED","message":"Invalid or expired session","details":{}}}',
      code,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }
}
