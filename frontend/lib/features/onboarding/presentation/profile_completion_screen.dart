import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/profile_provider.dart';

/// Profile completion — required before personalized suggestions.
///
/// BMI is NEVER an input here: the user enters height and pre-pregnancy
/// weight; the SERVER calculates and returns "Pre-pregnancy BMI".
/// Gestational week and trimester are likewise server-derived from the
/// LMP or due date. The screen only edits preferences and biometrics.
class ProfileCompletionScreen extends ConsumerStatefulWidget {
  const ProfileCompletionScreen({super.key});
  @override
  ConsumerState<ProfileCompletionScreen> createState() =>
      _ProfileCompletionScreenState();
}

class _ProfileCompletionScreenState
    extends ConsumerState<ProfileCompletionScreen> {
  final _heightCtrl = TextEditingController();
  final _weightCtrl = TextEditingController();
  final _lmpCtrl = TextEditingController();
  final _dislikeCtrl = TextEditingController();
  String _dietPref = 'veg';
  String? _cookingTime;
  String? _budget;
  final List<String> _allergies = [];
  final List<String> _dislikes = [];
  bool _saving = false;
  String? _localError;

  static const _allergyOptions = [
    ('peanut', 'Peanut'),
    ('tree_nut', 'Tree nuts'),
    ('milk', 'Milk / dairy'),
    ('egg', 'Egg'),
    ('wheat_gluten', 'Wheat / gluten'),
    ('soy', 'Soy'),
    ('fish', 'Fish'),
    ('shellfish', 'Shellfish'),
    ('sesame', 'Sesame'),
  ];

  @override
  void initState() {
    super.initState();
    Future.microtask(() async {
      await ref.read(profileProvider.notifier).loadCompletion();
      if (!mounted) return;
      final p = ref.read(profileProvider);
      if (p.heightCm != null) _heightCtrl.text = p.heightCm!.toString();
      if (p.prePregnancyWeightKg != null) {
        _weightCtrl.text = p.prePregnancyWeightKg!.toString();
      }
      setState(() {
        _allergies.addAll(p.allergies);
        _dislikes.addAll(p.dislikedIngredients);
        _dietPref = p.dietaryPreference ?? 'veg';
        _cookingTime = p.cookingTimePreference;
        _budget = p.budgetPreference;
      });
    });
  }

  @override
  void dispose() {
    _heightCtrl.dispose();
    _weightCtrl.dispose();
    _lmpCtrl.dispose();
    _dislikeCtrl.dispose();
    super.dispose();
  }

  int get _totalSteps => 5;

  int get _doneSteps {
    final p = ref.read(profileProvider);
    var done = 0;
    if (_heightCtrl.text.trim().isNotEmpty) done++;
    if (_weightCtrl.text.trim().isNotEmpty) done++;
    if (_lmpCtrl.text.trim().isNotEmpty || p.gestationalWeek != null) done++;
    done++; // region set at registration
    if (_allergies.isNotEmpty || p.allergies.isNotEmpty) done++;
    return done;
  }

  Future<void> _pickLmpDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now.subtract(const Duration(days: 100)),
      firstDate: now.subtract(const Duration(days: 340)),
      lastDate: now,
    );
    if (picked != null && mounted) {
      setState(() => _lmpCtrl.text =
          '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}');
    }
  }

  Future<void> _save() async {
    final l = AppLocalizations.of(context);
    final height = double.tryParse(_heightCtrl.text.trim());
    final weight = double.tryParse(_weightCtrl.text.trim());
    if (height == null || weight == null) {
      setState(() => _localError = l.tr('err_enter_height_weight'));
      return;
    }
    setState(() {
      _saving = true;
      _localError = null;
    });

    String? err = await ref.read(profileProvider.notifier).saveCoreProfile(
          heightCm: height,
          prePregnancyWeightKg: weight,
          lmpDate: _lmpCtrl.text.trim().isNotEmpty ? _lmpCtrl.text.trim() : null,
        );
    err ??= await ref.read(profileProvider.notifier).savePreferences(
          allergies: _allergies,
          dietaryPreference: _dietPref,
          dislikedIngredients: _dislikes,
          cookingTimePreference: _cookingTime,
          budgetPreference: _budget,
        );

    if (!mounted) return;
    setState(() => _saving = false);
    if (err != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(err),
        backgroundColor: AppColors.error,
        behavior: SnackBarBehavior.floating,
      ));
      return;
    }
    final complete = ref.read(profileProvider).complete;
    if (complete) {
      context.go('/diet');
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(l.tr('profile_saved_incomplete')),
        backgroundColor: AppColors.error,
        behavior: SnackBarBehavior.floating,
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final p = ref.watch(profileProvider);
    final progress = _doneSteps / _totalSteps;

    return Scaffold(
      appBar: AppBar(title: Text(l.tr('profile_completion_title'))),
      body: p.isLoading && _heightCtrl.text.isEmpty
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : ResponsiveSafeCenter(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Progress
                    Row(children: [
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: LinearProgressIndicator(
                            value: progress,
                            minHeight: 8,
                            backgroundColor: AppColors.primary.withValues(alpha: 0.1),
                            color: AppColors.primary,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text('${(progress * 100).round()}%',
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                    ]),
                    const SizedBox(height: 8),
                    Text(l.tr('profile_completion_hint'),
                        style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                    const SizedBox(height: 20),

                    // ── Server-calculated context (read-only) ──
                    if (p.prePregnancyBmi != null || p.gestationalWeek != null)
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.06),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppColors.primary.withValues(alpha: 0.15)),
                        ),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Icon(Icons.verified_user_outlined, size: 18, color: AppColors.primary),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(l.tr('server_calculated_note'),
                                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                            ),
                          ]),
                          const SizedBox(height: 12),
                          Row(children: [
                            _ServerStat(
                              label: l.tr('pre_pregnancy_bmi'),
                              value: p.prePregnancyBmi != null
                                  ? p.prePregnancyBmi!.toString()
                                  : '—',
                            ),
                            _ServerStat(
                              label: l.tr('pregnancy_week'),
                              value: p.gestationalWeek != null ? '${p.gestationalWeek}' : '—',
                            ),
                            _ServerStat(
                              label: l.tr('trimester'),
                              value: p.trimester != null ? '${p.trimester}' : '—',
                            ),
                          ]),
                        ]),
                      ),
                    const SizedBox(height: 20),

                    // ── Inputs ──
                    _label(l.tr('height_cm_label')),
                    TextField(
                      controller: _heightCtrl,
                      keyboardType: TextInputType.number,
                      decoration: _dec(l.tr('height_cm_hint')),
                    ),
                    const SizedBox(height: 14),
                    _label(l.tr('prepreg_weight_label')),
                    TextField(
                      controller: _weightCtrl,
                      keyboardType: TextInputType.number,
                      decoration: _dec(l.tr('prepreg_weight_hint')),
                    ),
                    const SizedBox(height: 14),
                    _label(l.tr('lmp_date_label')),
                    TextField(
                      controller: _lmpCtrl,
                      readOnly: true,
                      onTap: _pickLmpDate,
                      decoration: _dec(l.tr('lmp_date_hint')).copyWith(
                        suffixIcon: const Icon(Icons.calendar_month_outlined),
                      ),
                    ),
                    const SizedBox(height: 14),
                    _label(l.tr('dietary_pref')),
                    _prefChips(),
                    const SizedBox(height: 14),
                    _label(l.tr('allergies_label')),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: _allergyOptions.map((opt) {
                        final selected = _allergies.contains(opt.$1);
                        return FilterChip(
                          label: Text(opt.$2, style: const TextStyle(fontSize: 13)),
                          selected: selected,
                          onSelected: (v) => setState(() {
                            v ? _allergies.add(opt.$1) : _allergies.remove(opt.$1);
                          }),
                          selectedColor: AppColors.primary.withValues(alpha: 0.15),
                          checkmarkColor: AppColors.primary,
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 14),
                    _label(l.tr('cooking_time_label')),
                    _optionChips(
                      options: const [('quick', 'Quick (< 20 min)'), ('moderate', 'Moderate'), ('relaxed', 'Relaxed')],
                      value: _cookingTime,
                      onSelected: (v) => setState(() => _cookingTime = v),
                    ),
                    const SizedBox(height: 14),
                    _label(l.tr('budget_label')),
                    _optionChips(
                      options: const [('low', 'Budget-friendly'), ('medium', 'Medium'), ('high', 'No limit')],
                      value: _budget,
                      onSelected: (v) => setState(() => _budget = v),
                    ),
                    const SizedBox(height: 14),
                    _label(l.tr('dislikes_label')),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          controller: _dislikeCtrl,
                          decoration: _dec(l.tr('dislikes_hint')),
                          onSubmitted: (_) => _addDislike(),
                        ),
                      ),
                      IconButton(
                        onPressed: _addDislike,
                        icon: const Icon(Icons.add_circle, color: AppColors.primary),
                      ),
                    ]),
                    if (_dislikes.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Wrap(
                          spacing: 8,
                          children: _dislikes
                              .map((d) => Chip(
                                    label: Text(d, style: const TextStyle(fontSize: 12)),
                                    onDeleted: () => setState(() => _dislikes.remove(d)),
                                  ))
                              .toList(),
                        ),
                      ),

                    if (_localError != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 16),
                        child: Text(_localError!,
                            style: const TextStyle(color: AppColors.error, fontSize: 13)),
                      ),
                    const SizedBox(height: 24),
                    SizedBox(
                      height: 54,
                      child: ElevatedButton(
                        onPressed: _saving ? null : _save,
                        style: ElevatedButton.styleFrom(
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                        ),
                        child: _saving
                            ? const SizedBox(
                                width: 22, height: 22,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : Text(l.tr('save_and_continue'),
                                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                      ),
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
    );
  }

  void _addDislike() {
    final v = _dislikeCtrl.text.trim().toLowerCase();
    if (v.isNotEmpty && !_dislikes.contains(v)) {
      setState(() => _dislikes.add(v));
    }
    _dislikeCtrl.clear();
  }

  Widget _prefChips() => Wrap(
        spacing: 8,
        children: [
          ('veg', 'Vegetarian'),
          ('eggetarian', 'Eggetarian'),
          ('nonveg', 'Non-vegetarian'),
        ].map((opt) {
          final selected = _dietPref == opt.$1;
          return ChoiceChip(
            label: Text(opt.$2, style: const TextStyle(fontSize: 13)),
            selected: selected,
            onSelected: (_) => setState(() => _dietPref = opt.$1),
            selectedColor: AppColors.primary.withValues(alpha: 0.15),
            checkmarkColor: AppColors.primary,
          );
        }).toList(),
      );

  Widget _optionChips({
    required List<(String, String)> options,
    required String? value,
    required ValueChanged<String?> onSelected,
  }) =>
      Wrap(
        spacing: 8,
        children: options.map((opt) {
          final selected = value == opt.$1;
          return ChoiceChip(
            label: Text(opt.$2, style: const TextStyle(fontSize: 13)),
            selected: selected,
            onSelected: (v) => onSelected(v ? opt.$1 : null),
            selectedColor: AppColors.primary.withValues(alpha: 0.15),
            checkmarkColor: AppColors.primary,
          );
        }).toList(),
      );

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(text,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      );

  InputDecoration _dec(String hint) => InputDecoration(
        hintText: hint,
        filled: true,
        fillColor: AppColors.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      );
}

class _ServerStat extends StatelessWidget {
  final String label;
  final String value;
  const _ServerStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(children: [
        Text(value,
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800,
                color: AppColors.primary)),
        const SizedBox(height: 2),
        Text(label,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
      ]),
    );
  }
}

class ResponsiveSafeCenter extends StatelessWidget {
  final Widget child;
  const ResponsiveSafeCenter({super.key, required this.child});
  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: child,
        ),
      ),
    );
  }
}
