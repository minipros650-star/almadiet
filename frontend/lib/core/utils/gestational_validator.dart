/// Client-side gestational-age validation.
///
/// Mirrors backend/app/domain/gestational.py — the two MUST stay in sync
/// (enforced by test/gestational_parity_test.dart). The backend remains the
/// authority; this exists to give instant form feedback.
class GestationalValidator {
  static const Map<int, (int, int)> trimesterWeekRanges = {
    1: (1, 13),
    2: (14, 26),
    3: (27, 42),
  };

  static const int minWeek = 1;
  static const int maxWeek = 42;

  /// Returns null if valid, otherwise a human-readable error message.
  /// Message format matches the backend error text.
  static String? validate(int trimester, int week) {
    if (week < minWeek || week > maxWeek) {
      return 'Week must be between $minWeek and $maxWeek';
    }
    final range = trimesterWeekRanges[trimester];
    if (range == null) return 'Invalid trimester';
    if (week < range.$1 || week > range.$2) {
      return 'Week $week is not in trimester $trimester (weeks ${range.$1}-${range.$2})';
    }
    return null;
  }
}
