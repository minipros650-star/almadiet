/// Client-side validation for optional vital fields, mirroring the backend
/// Pydantic schema exactly (backend/app/schemas/health.py).
///
/// All fields are optional: blank is valid. A value present must be a number
/// within the physiological bounds below — matching the server so a value the
/// form accepts is never rejected by the API, and the form rejects anything
/// the API would reject before it's sent.
library;

/// One vital field: backend field name, physiological bounds, and a
/// human-readable range hint.
class VitalField {
  final String backendField;
  final double min;
  final double max;

  const VitalField({
    required this.backendField,
    required this.min,
    required this.max,
  });

  /// Returns a validation error *template*, or null if [value] (blank-allowed)
  /// is valid. Templates: 'number' (not a number), or a message containing
  /// {min}/{max} placeholders. The caller localizes and substitutes bounds.
  String? validate(String value) {
    final v = value.trim();
    if (v.isEmpty) return null; // optional field
    final n = double.tryParse(v);
    if (n == null) return 'number';
    if (n < min || n > max) return '{min}–{max}';
    return null;
  }
}

/// Bounds mirror backend/app/schemas/health.py — keep in sync.
class VitalFields {
  static const weight = VitalField(backendField: 'current_weight_kg', min: 30, max: 200);
  static const hemoglobin = VitalField(backendField: 'hemoglobin', min: 3, max: 20);
  static const bpSystolic = VitalField(backendField: 'blood_pressure_sys', min: 60, max: 250);
  static const bpDiastolic = VitalField(backendField: 'blood_pressure_dia', min: 40, max: 150);
  static const fastingSugar = VitalField(backendField: 'blood_sugar_fasting', min: 20, max: 600);
}
