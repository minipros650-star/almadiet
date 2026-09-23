# Accessibility & Internationalization

**Status:** Implemented practices + automated tests

## Accessibility (WCAG-aligned targets)
- **Contrast:** body text ≥ 4.5:1 on its background; the legacy `textSecondary
  #7A6B80` on white passes; primary-pink is never used for small body text on
  white.
- **Touch targets:** ≥ 48×48 dp for all interactive elements (chips, tabs,
  buttons enforce min sizes in shared widgets).
- **Scaling:** layouts tested with `textScaleFactor` 1.0 / 1.3 / 2.0;
  `maxLines` + `TextOverflow.ellipsis` with `minLines` reserved so cards grow
  instead of clipping.
- **Screen readers:** all icons-only buttons have `Semantics`/`tooltip`
  labels; meal cards expose a single merged semantics node
  ("{name}, {calories} calories, allergens: {list}").
- **Color independence:** status always pairs color with icon + text
  (ACTIVE/RESOLVED, warning banners have ⚠ icon AND text).
- **Safety info:** never communicated by color alone (allergy chips include
  the allergen name in text).

## Localization
Five languages, all production-complete:
`en` English · `ml` മലയാളം · `ta` தமிழ் · `kn` ಕನ್ನಡ · `te` తెలుగు.

- Single source of truth: `frontend/lib/core/localization/app_localizations.dart`
  with **`en` as the canonical key set**; every other locale must define every
  key — enforced by `frontend/test/localization_test.dart`, which fails on any
  missing or extra key and on untranslated English text in non-English locales
  (heuristic: exact-match with English value for non-brand keys).
- No accidental English fallback for production-visible content (the runtime
  `tr()` fallback remains as a crash-safety net but is treated as a test
  failure condition upstream).
- Numbers, dates and units use `intl` with locale-aware formatting; units
  (kg, g/dL, mmHg, mg, mcg) are part of translation strings so word order can
  change per language.
- Long translated strings: Malayalam/Tamil strings are set ~15% longer than
  English for layout testing; `test/widget_overflow_test.dart` renders the
  longest strings at 320px width.

## Known limitations
- Regional meal **names** may fall back to English when the dataset lacks a
  translation (displayed as-is; not hidden).
- Machine-aided translations were reviewed by contributors but not by
  certified translators for all four languages; flagged in RELEASE_CHECKLIST.
