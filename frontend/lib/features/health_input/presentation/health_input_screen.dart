import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/widgets/loading_animations.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/health_provider.dart';
import '../../../providers/diet_provider.dart';

class HealthInputScreen extends ConsumerStatefulWidget {
  const HealthInputScreen({super.key});
  @override
  ConsumerState<HealthInputScreen> createState() => _HealthInputScreenState();
}

class _HealthInputScreenState extends ConsumerState<HealthInputScreen> with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  int _trimester = 1;
  int _week = 12;
  final _weightCtrl = TextEditingController();
  final _hbCtrl = TextEditingController();
  final _bpSysCtrl = TextEditingController();
  final _bpDiaCtrl = TextEditingController();
  final _sugarCtrl = TextEditingController();
  bool _isVeg = false;
  String _dietPref = 'nonveg';
  bool _autoGenerate = true;
  bool _submitting = false;
  late AnimationController _animCtrl;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 700))..forward();
  }

  @override
  void dispose() { _animCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);

    if (_submitting) {
      return Scaffold(body: PregnancyLoader(message: l.tr('analyzing')));
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(l.tr('health_input')),
        leading: IconButton(icon: const Icon(Icons.arrow_back_ios_rounded), onPressed: () => context.pop()),
      ),
      body: FadeTransition(
        opacity: CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut),
        child: ResponsiveCenter(
          child: SingleChildScrollView(
            padding: Responsive.screenPadding(context).copyWith(top: 16, bottom: 32),
            child: Form(
              key: _formKey,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                // Header tip
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(colors: [AppColors.primary.withValues(alpha: 0.06), AppColors.secondary.withValues(alpha: 0.04)]),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Row(children: [
                    const Text('💡', style: TextStyle(fontSize: 22)),
                    const SizedBox(width: 12),
                    Expanded(child: Text(l.tr('health_tip'), style: TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4))),
                  ]),
                ),
                const SizedBox(height: 24),

                // ── Section: Pregnancy Info ──
                _SectionTitle(icon: Icons.child_care, title: l.tr('pregnancy_info'), color: AppColors.primary),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(child: _dropdown(l.tr('trimester'), _trimester, {1: l.tr('first'), 2: l.tr('second'), 3: l.tr('third')}, (v) => setState(() { _trimester = v; _week = [12, 20, 32][v - 1]; }))),
                  const SizedBox(width: 14),
                  Expanded(child: _buildField(l.tr('week'), TextEditingController(text: '$_week'), TextInputType.number, icon: Icons.calendar_today_outlined)),
                ]),
                const SizedBox(height: 20),

                // ── Section: Vitals ──
                _SectionTitle(icon: Icons.monitor_heart, title: l.tr('health_vitals'), color: AppColors.error),
                const SizedBox(height: 12),
                _buildField(l.tr('weight'), _weightCtrl, TextInputType.number, icon: Icons.monitor_weight_outlined),
                const SizedBox(height: 12),
                _buildField(l.tr('hemoglobin'), _hbCtrl, TextInputType.number, icon: Icons.bloodtype_outlined),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(child: _buildField(l.tr('bp_systolic'), _bpSysCtrl, TextInputType.number, icon: Icons.favorite_outline)),
                  const SizedBox(width: 14),
                  Expanded(child: _buildField(l.tr('bp_diastolic'), _bpDiaCtrl, TextInputType.number, icon: Icons.favorite_border)),
                ]),
                const SizedBox(height: 12),
                _buildField(l.tr('fasting_sugar'), _sugarCtrl, TextInputType.number, icon: Icons.water_drop_outlined),
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
                    onPressed: _submit,
                    icon: const Icon(Icons.auto_awesome, size: 20),
                    label: Text(l.tr('submit_generate'), style: const TextStyle(fontSize: 16)),
                    style: ElevatedButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)), elevation: 4, shadowColor: AppColors.primary.withValues(alpha: 0.3)),
                  ),
                ),
              ]),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildField(String hint, TextEditingController ctrl, TextInputType type, {IconData? icon}) {
    return TextField(controller: ctrl, keyboardType: type, decoration: InputDecoration(hintText: hint, prefixIcon: icon != null ? Icon(icon, color: AppColors.primary.withValues(alpha: 0.6)) : null));
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
    setState(() => _submitting = true);

    final data = {
      'trimester': _trimester, 'week_number': _week,
      'current_weight_kg': double.tryParse(_weightCtrl.text) ?? 60,
      'bmi': 24.0,
      'blood_pressure_sys': double.tryParse(_bpSysCtrl.text) ?? 120,
      'blood_pressure_dia': double.tryParse(_bpDiaCtrl.text) ?? 80,
      'hemoglobin': double.tryParse(_hbCtrl.text) ?? 11,
      'blood_sugar_fasting': double.tryParse(_sugarCtrl.text) ?? 90,
      'allergies': <String>[], 'medical_conditions': <String>[],
      'is_vegetarian': _isVeg, 'dietary_preference': _dietPref,
    };

    final recordId = await ref.read(healthProvider.notifier).submitRecord(data);
    if (recordId != null && _autoGenerate) {
      await ref.read(dietProvider.notifier).generatePlan(recordId);
    }

    if (mounted) {
      setState(() => _submitting = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(recordId != null ? l.tr('health_submitted') : l.tr('health_failed')),
        backgroundColor: recordId != null ? AppColors.success : AppColors.error,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ));
      if (recordId != null) context.go('/home');
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
