import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/utils/gestational_validator.dart';
import '../../../core/utils/vital_field_validator.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/health_provider.dart';
import '../../../providers/diet_provider.dart';
import '../../../providers/profile_provider.dart';
import '../../../providers/auth_provider.dart';

class HealthInputScreen extends ConsumerStatefulWidget {
  const HealthInputScreen({super.key});
  @override
  ConsumerState<HealthInputScreen> createState() => _HealthInputScreenState();
}

class _HealthInputScreenState extends ConsumerState<HealthInputScreen> {
  final _formKey = GlobalKey<FormState>();
  int _trimester = 1;
  int _week = 12;
  final _weightCtrl = TextEditingController();
  final _bpSysCtrl = TextEditingController();
  final _bpDiaCtrl = TextEditingController();
  final _hbCtrl = TextEditingController();
  final _sugarCtrl = TextEditingController();
  final _allergyCtrl = TextEditingController();
  bool _isVeg = false;
  String _dietPref = 'veg';
  bool _autoGenerate = true;
  bool _submitting = false;
  final List<String> _allergies = [];
  String? _gestationalError;
  // Per-field validation errors, keyed by controller.
  final Map<TextEditingController, String> _vitalErrors = {};  /// Validate one vital controller; updates the inline error map.
  void _validateVital(TextEditingController ctrl, VitalField spec) {
    final l = AppLocalizations.of(context);
    final raw = spec.validate(ctrl.text);
    String? err;
    if (raw == 'number') {
      err = l.tr('err_must_be_number');
    } else if (raw != null) {
      final range = l
          .tr('err_must_be_between')
          .replaceAll('{min}', spec.min.round().toString())
          .replaceAll('{max}', spec.max.round().toString());
      err = range;
    }
    setState(() {
      if (raw == null) {
        _vitalErrors.remove(ctrl);
      } else {
        _vitalErrors[ctrl] = err ?? '';
        _gestationalError = null; // clear stale global error
      }
    });
  }

  bool get _vitalsValid => _vitalErrors.isEmpty;

  @override
  void dispose() {
    _weightCtrl.dispose();
    _bpSysCtrl.dispose();
    _bpDiaCtrl.dispose();
    _hbCtrl.dispose();
    _sugarCtrl.dispose();
    _allergyCtrl.dispose();
    super.dispose();
  }

  void _onTrimesterOrWeekChanged() {
    setState(() {
      _gestationalError = GestationalValidator.validate(_trimester, _week);
    });
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);

    if (_submitting) {
      return Scaffold(
        appBar: AppBar(title: Text(l.tr('health_input'))),
        body: Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const CircularProgressIndicator(color: AppColors.primary),
            const SizedBox(height: 20),
            Text(l.tr('analyzing'), textAlign: TextAlign.center, style: const TextStyle(fontSize: 15, height: 1.5)),
          ]),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(l.tr('health_input')),
        leading: IconButton(icon: const Icon(Icons.arrow_back_ios_rounded), onPressed: () => context.pop()),
      ),
      body: ResponsiveCenter(
        child: SingleChildScrollView(
          padding: Responsive.screenPadding(context).copyWith(top: 16, bottom: 32),
          child: Form(
            key: _formKey,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              // Header tip — transparent about what the app does/doesn't do.
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: [AppColors.primary.withValues(alpha: 0.06), AppColors.secondary.withValues(alpha: 0.04)]),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(Icons.info_outline_rounded, size: 22, color: AppColors.primary),
                  const SizedBox(width: 12),
                  Expanded(child: Text(l.tr('health_tip'), style: TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4))),
                ]),
              ),
              const SizedBox(height: 24),

              // ── Section: Pregnancy Info ──
              _SectionTitle(icon: Icons.child_care, title: l.tr('pregnancy_info'), color: AppColors.primary),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: _dropdown(l.tr('trimester'), _trimester, {1: l.tr('first'), 2: l.tr('second'), 3: l.tr('third')}, (v) {
                  setState(() { _trimester = v; _week = [12, 20, 32][v - 1]; });
                  _onTrimesterOrWeekChanged();
                })),
                const SizedBox(width: 14),
                Expanded(child: _buildField(l.tr('week'), TextEditingController(text: '$_week'), TextInputType.number,
                  icon: Icons.calendar_today_outlined,
                  onChanged: (v) {
                    final parsed = int.tryParse(v);
                    if (parsed != null) {
                      _week = parsed;
                      _onTrimesterOrWeekChanged();
                    }
                  })),
              ]),
              if (_gestationalError != null) ...[
                const SizedBox(height: 8),
                // Icon + text: color is never the only signal.
                Row(children: [
                  Icon(Icons.error_outline_rounded, size: 16, color: AppColors.error),
                  const SizedBox(width: 6),
                  Expanded(child: Text(_gestationalError!, style: TextStyle(fontSize: 12, color: AppColors.error))),
                ]),
              ],
              const SizedBox(height: 20),

              // ── Section: Vitals (all optional — nothing is invented) ──
              _SectionTitle(icon: Icons.monitor_heart, title: l.tr('health_vitals'), color: AppColors.error),
              const SizedBox(height: 4),
              Padding(
                padding: const EdgeInsets.only(top: 2, bottom: 10),
                child: Text(l.tr('vitals_optional'), style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              ),
              _buildVitalField(l.tr('weight'), _weightCtrl, VitalFields.weight, icon: Icons.monitor_weight_outlined, hintKey: 'vital_hint_weight'),
              const SizedBox(height: 12),
              _buildVitalField(l.tr('hemoglobin'), _hbCtrl, VitalFields.hemoglobin, icon: Icons.bloodtype_outlined, hintKey: 'vital_hint_hemoglobin'),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: _buildVitalField(l.tr('bp_systolic'), _bpSysCtrl, VitalFields.bpSystolic, icon: Icons.favorite_outline, hintKey: 'vital_hint_bp_sys')),
                const SizedBox(width: 14),
                Expanded(child: _buildVitalField(l.tr('bp_diastolic'), _bpDiaCtrl, VitalFields.bpDiastolic, icon: Icons.favorite_border, hintKey: 'vital_hint_bp_dia')),
              ]),
              const SizedBox(height: 12),
              _buildVitalField(l.tr('fasting_sugar'), _sugarCtrl, VitalFields.fastingSugar, icon: Icons.water_drop_outlined, hintKey: 'vital_hint_sugar'),
              const SizedBox(height: 24),

              // ── Section: Allergies (hard safety filter) ──
              _SectionTitle(icon: Icons.report_rounded, title: l.tr('allergies'), color: AppColors.warning),
              const SizedBox(height: 4),
              Padding(
                padding: const EdgeInsets.only(top: 2, bottom: 10),
                child: Text(l.tr('allergies_hint'), style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              ),
              Row(children: [
                Expanded(child: TextField(
                  controller: _allergyCtrl,
                  decoration: InputDecoration(hintText: l.tr('allergy_placeholder')),
                  onSubmitted: _addAllergy,
                )),
                const SizedBox(width: 10),
                IconButton(
                  onPressed: () => _addAllergy(_allergyCtrl.text),
                  icon: Icon(Icons.add_circle_rounded, color: AppColors.primary, size: 30),
                  tooltip: l.tr('add_allergy'),
                ),
              ]),
              if (_allergies.isNotEmpty) ...[
                const SizedBox(height: 10),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final a in _allergies)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: AppColors.warning.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.warning.withValues(alpha: 0.3)),
                      ),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        Icon(Icons.block_rounded, size: 14, color: AppColors.warning),
                        const SizedBox(width: 6),
                        Text(a, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.warning)),
                        const SizedBox(width: 6),
                        GestureDetector(
                          onTap: () => setState(() => _allergies.remove(a)),
                          child: Icon(Icons.close_rounded, size: 14, color: AppColors.warning),
                        ),
                      ]),
                    ),
                ]),
              ],
              const SizedBox(height: 24),

              // ── Section: Dietary Preference ──
              _SectionTitle(icon: Icons.restaurant, title: l.tr('dietary_pref'), color: AppColors.secondary),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 10)]),
                child: Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
                  _DietChoice(emoji: '🥩', label: l.tr('non_veg'), selected: _dietPref == 'nonveg', onTap: () => setState(() { _dietPref = 'nonveg'; _isVeg = false; })),
                  _DietChoice(emoji: '🥬', label: l.tr('veg'), selected: _dietPref == 'veg', onTap: () => setState(() { _dietPref = 'veg'; _isVeg = true; })),
                  _DietChoice(emoji: '🥚', label: l.tr('eggetarian'), selected: _dietPref == 'eggetarian', onTap: () => setState(() { _dietPref = 'eggetarian'; _isVeg = false; })),
                ]),
              ),
              const SizedBox(height: 16),

              // Auto-generate toggle
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 10)]),
                child: SwitchListTile(
                  title: Text(l.tr('auto_generate'), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  subtitle: Text(l.tr('generate_after'), style: const TextStyle(fontSize: 12)),
                  value: _autoGenerate,
                  onChanged: (v) => setState(() => _autoGenerate = v),
                  activeThumbColor: AppColors.primary,
                  contentPadding: EdgeInsets.zero,
                ),
              ),
              const SizedBox(height: 28),

              // Submit
              SizedBox(
                height: 58,
                child: ElevatedButton.icon(
                  onPressed: _gestationalError == null ? _submit : null,
                  icon: const Icon(Icons.restaurant_menu_rounded, size: 20),
                  label: Text(l.tr('submit_generate'), style: const TextStyle(fontSize: 16)),
                  style: ElevatedButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }

  void _addAllergy(String value) {
    final v = value.trim();
    if (v.isEmpty || _allergies.contains(v.toLowerCase())) return;
    setState(() {
      _allergies.add(v.toLowerCase());
      _allergyCtrl.clear();
    });
  }

  /// Vital field with inline range validation mirroring the backend schema.
  Widget _buildVitalField(String hint, TextEditingController ctrl, VitalField spec,
      {IconData? icon, String? hintKey}) {
    final l = AppLocalizations.of(context);
    final error = _vitalErrors[ctrl];
    return TextField(
      controller: ctrl,
      keyboardType: TextInputType.number,
      onChanged: (_) => _validateVital(ctrl, spec),
      decoration: InputDecoration(
        hintText: hint,
        prefixIcon: icon != null ? Icon(icon, color: AppColors.primary.withValues(alpha: 0.6)) : null,
        errorText: error,
        helperText: hintKey != null ? l.tr(hintKey) : null,
        helperStyle: const TextStyle(fontSize: 11),
      ),
    );
  }

  Widget _buildField(String hint, TextEditingController ctrl, TextInputType type, {IconData? icon, Function(String)? onChanged}) {
    return TextField(
      controller: ctrl,
      keyboardType: type,
      onChanged: onChanged,
      decoration: InputDecoration(hintText: hint, prefixIcon: icon != null ? Icon(icon, color: AppColors.primary.withValues(alpha: 0.6)) : null),
    );
  }

  Widget _dropdown<T>(String label, T value, Map<T, String> items, Function(T) onChanged) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(color: AppColors.inputFill, borderRadius: BorderRadius.circular(14)),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<T>(value: value, isExpanded: true, items: items.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value, style: const TextStyle(fontSize: 14)))).toList(), onChanged: (v) => onChanged(v as T)),
      ),
    );
  }

  Future<void> _submit() async {
    final l = AppLocalizations.of(context);
    if (GestationalValidator.validate(_trimester, _week) != null) return;

    // Validate every vital, including untouched fields with content.
    for (final entry in {
      _weightCtrl: VitalFields.weight,
      _hbCtrl: VitalFields.hemoglobin,
      _bpSysCtrl: VitalFields.bpSystolic,
      _bpDiaCtrl: VitalFields.bpDiastolic,
      _sugarCtrl: VitalFields.fastingSugar,
    }.entries) {
      _validateVital(entry.key, entry.value);
    }
    if (!_vitalsValid) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(l.tr('fix_errors_first')),
        backgroundColor: AppColors.error,
        behavior: SnackBarBehavior.floating,
      ));
      return;
    }

    if (!mounted) return;
    setState(() => _submitting = true);

    // Only explicitly entered vitals are sent — nothing is fabricated.
    final data = <String, dynamic>{
      'trimester': _trimester,
      'week_number': _week,
      'current_weight_kg': double.tryParse(_weightCtrl.text),
      'blood_pressure_sys': double.tryParse(_bpSysCtrl.text),
      'blood_pressure_dia': double.tryParse(_bpDiaCtrl.text),
      'hemoglobin': double.tryParse(_hbCtrl.text),
      'blood_sugar_fasting': double.tryParse(_sugarCtrl.text),
      'allergies': _allergies,
      'medical_conditions': <String>[],
      'is_vegetarian': _isVeg,
      'dietary_preference': _dietPref,
    };
    data.removeWhere((_, v) => v == null);

    final error = await ref.read(healthProvider.notifier).createRecord(data);
    if (error == null && _autoGenerate) {
      final records = ref.read(healthProvider).records;
      final recordId = records.isNotEmpty ? records.first['id'] : null;
      if (recordId != null) {
        final result =
            await ref.read(dietProvider.notifier).generatePlan(recordId.toString());
        if (result && mounted) {
          // Plan generated — show it immediately instead of a dead end.
          setState(() => _submitting = false);
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(l.tr('health_submitted')),
            backgroundColor: AppColors.success,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ));
          context.go('/diet');
          return;
        }
        // Plan generation refused: route to the blocking reason's screen
        // (consent first — privacy gate — then the diet screen's safe
        // blocking states: profile incomplete, clinician review, no safe
        // suggestion). Never pretend submission succeeded.
        if (!result && mounted) {
          final code = ref.read(dietProvider).blockingCode;
          if (code == SuggestionBlock.consentRequired) {
            await ref.read(authStateProvider.notifier).refreshConsentRequired();
            if (mounted) context.go('/consent');
            return;
          }
          if (code == SuggestionBlock.profileIncomplete) {
            if (mounted) context.go('/profile-completion');
            return;
          }
          // clinician review / no-safe-suggestion / other: the diet screen
          // renders the matching safe state from dietProvider.blockingCode.
          if (mounted) context.go('/diet');
          return;
        }
      }
    }

    if (mounted) {
      setState(() => _submitting = false);
      if (error == null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(l.tr('health_submitted')),
          backgroundColor: AppColors.success,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ));
        context.go('/home');
      } else if (error == kConsentRequired) {
        // Consent gate: send the user to the consent screen, not a dead end.
        await ref.read(authStateProvider.notifier).refreshConsentRequired();
        if (mounted) context.go('/consent');
      } else {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(error),
          backgroundColor: AppColors.error,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ));
      }
    }
  }
}

class _SectionTitle extends StatelessWidget {
  final IconData icon; final String title; final Color color;
  const _SectionTitle({required this.icon, required this.title, required this.color});
  @override
  Widget build(BuildContext context) => Row(children: [
    Container(width: 32, height: 32, decoration: BoxDecoration(color: color.withValues(alpha: 0.1), shape: BoxShape.circle), child: Icon(icon, size: 16, color: color)),
    const SizedBox(width: 10),
    Text(title, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color)),
  ]);
}

class _DietChoice extends StatelessWidget {
  final String emoji, label;
  final bool selected;
  final VoidCallback onTap;
  const _DietChoice({required this.emoji, required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: selected ? AppColors.primary.withValues(alpha: 0.1) : Colors.transparent,
        borderRadius: BorderRadius.circular(14),
        border: selected ? Border.all(color: AppColors.primary.withValues(alpha: 0.3)) : null,
      ),
      child: Column(children: [
        Text(emoji, style: const TextStyle(fontSize: 24)),
        const SizedBox(height: 4),
        Text(label, style: TextStyle(fontSize: 12, fontWeight: selected ? FontWeight.w700 : FontWeight.w500, color: selected ? AppColors.primary : AppColors.textSecondary)),
      ]),
    ),
  );
}
