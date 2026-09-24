import 'package:dio/dio.dart';

/// True when [e] is the backend's 409 CONSENT_REQUIRED rejection.
bool isConsentRequiredError(Object e) {
  if (e is DioException) {
    final data = e.response?.data;
    final error = data is Map ? data['error'] : null;
    final code = error is Map ? error['code'] : null;
    if (code == 'CONSENT_REQUIRED') return true;
    // Fallback: any 409 from a data endpoint means the consent gate.
    return e.response?.statusCode == 409;
  }
  return false;
}
