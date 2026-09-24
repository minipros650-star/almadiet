import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:almadiet/core/localization/app_localizations.dart';

/// TEST: claims gate — user-visible strings must never contain unsupported
/// clinical or regulatory claims (docs/CLINICAL_SAFETY.md §claims).
void main() {
  /// Phrases that are only acceptable inside NEGATED safety disclaimers
  /// ("does not diagnose", "not used to diagnose"). The negation test below
  /// allows those two documented disclaimer keys; everywhere else the bare
  /// phrase is a violation.
  const forbidden = [
    // Unsupported clinical claims
    'clinically approved', 'clinically validated', 'clinically proven',
    'medically approved', 'medically validated', 'doctor approved',
    'who approved', 'who certified', 'medically safe',
    // Treatment/diagnosis language
    'diagnosis', 'diagnose', 'treatment', 'cure', 'emergency treatment',
    // Fabricated authority
    'ai doctor', 'clinical ai', 'guaranteed',
  ];

  /// Keys that exist solely to state what the app does NOT do. A match there
  /// is only a violation if the sentence around the phrase is not a negation.
  const disclaimerKeys = {'health_tip', 'consent_body', 'urgent_disclaimer_fallback', 'urgent_app_cannot'};
  const negationMarkers = ['not ', 'never ', "doesn't", 'does not', 'cannot'];

  bool isInsideNegation(String value, String phrase) {
    // Look at the sentence containing the phrase; it must contain a
    // negation marker for the claim to be a disclaimer rather than a claim.
    final lower = value.toLowerCase();
    var idx = lower.indexOf(phrase);
    while (idx != -1) {
      final sentenceStart = lower.lastIndexOf('.', idx) + 1;
      final sentenceEnd = lower.indexOf('.', idx);
      final sentence = lower.substring(
        sentenceStart,
        sentenceEnd == -1 ? lower.length : sentenceEnd,
      ).trim();
      if (!negationMarkers.any(sentence.contains)) {
        return false;
      }
      idx = lower.indexOf(phrase, idx + 1);
    }
    return true;
  }

  const langs = ['en', 'ml', 'ta', 'kn', 'te'];

  test('no localization string contains forbidden clinical claims', () {
    final violations = <String>[];
    for (final lang in langs) {
      for (final key in AppLocalizations.keysFor(lang)) {
        final value = _tr(lang, key);
        final lower = value.toLowerCase();
        for (final phrase in forbidden) {
          if (!lower.contains(phrase)) continue;
          final allowed =
              disclaimerKeys.contains(key) && isInsideNegation(value, phrase);
          if (!allowed) {
            violations.add('$lang/$key contains "$phrase": "$value"');
          }
        }
      }
    }
    expect(violations, isEmpty, reason: violations.join('\n'));
  });

  test('English disclaimers explicitly deny diagnosis/treatment', () {
    final l = AppLocalizations(const Locale('en'));
    expect(l.tr('consent_body'), contains('does not diagnose'));
    expect(l.tr('urgent_disclaimer_fallback'), contains('not medical advice'));
    expect(l.tr('urgent_disclaimer_fallback'), contains('cannot assess'));
  });
}

// The localized values map is private; mirror the public tr() lookup using
// a non-UI locale path.
String _tr(String lang, String key) {
  final loc = AppLocalizations(Locale(lang));
  return loc.tr(key);
}
