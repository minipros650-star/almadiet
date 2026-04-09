import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/widgets/loading_animations.dart';
import '../../../core/widgets/meal_image.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/diet_provider.dart';

class DietPlanScreen extends ConsumerStatefulWidget {
  const DietPlanScreen({super.key});
  @override
  ConsumerState<DietPlanScreen> createState() => _DietPlanScreenState();
}

class _DietPlanScreenState extends ConsumerState<DietPlanScreen> with SingleTickerProviderStateMixin {
  late AnimationController _animCtrl;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..forward();
    Future.microtask(() => ref.read(dietProvider.notifier).loadPlans());
  }

  @override
  void dispose() { _animCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final diet = ref.watch(dietProvider);
    final l = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l.tr('diet_plan'))),
      body: diet.isLoading
          ? PregnancyLoader(message: l.tr('loading_meal_plan'))
          : diet.currentPlan == null
              ? _EmptyState()
              : FadeTransition(
                  opacity: CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut),
                  child: ResponsiveCenter(child: _PlanView(plan: diet.currentPlan!, onMealTap: (id) {
                    if (id.isNotEmpty && context.mounted) {
                      debugPrint('🚀 Diet: Navigating to /meal/$id');
                      GoRouter.of(context).push('/meal/$id');
                    }
                  })),
                ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Center(child: ResponsiveCenter(child: Padding(
      padding: const EdgeInsets.all(40),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Container(
          width: 100, height: 100,
          decoration: BoxDecoration(color: AppColors.secondary.withValues(alpha: 0.08), shape: BoxShape.circle),
          child: const Center(child: Text('🍽️', style: TextStyle(fontSize: 44))),
        ),
        const SizedBox(height: 20),
        Text(l.tr('no_diet_plan'), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Text(l.tr('no_diet_desc'), style: TextStyle(color: AppColors.textSecondary, height: 1.5), textAlign: TextAlign.center),
        const SizedBox(height: 28),
        ElevatedButton.icon(
          onPressed: () => context.push('/health-input'),
          icon: const Icon(Icons.add_rounded),
          label: Text(l.tr('add_health_data')),
          style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
        ),
      ]),
    )));
  }
}

class _PlanView extends StatelessWidget {
  final Map<String, dynamic> plan;
  final Function(String) onMealTap;
  const _PlanView({required this.plan, required this.onMealTap});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return ListView(padding: Responsive.screenPadding(context).copyWith(top: 16, bottom: 32), children: [
      // Nutrient targets header
      Container(
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(gradient: AppColors.primaryGradient, borderRadius: BorderRadius.circular(22), boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.25), blurRadius: 16, offset: const Offset(0, 6))]),
        child: Column(children: [
          Text(l.tr('daily_targets'), style: const TextStyle(fontSize: 13, color: Colors.white70)),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: _PlanStat('🔥', '${plan['target_calories']?.toInt() ?? '-'}', l.tr('calories'))),
            Expanded(child: _PlanStat('💪', '${plan['target_protein']?.toInt() ?? '-'}g', l.tr('protein'))),
            Expanded(child: _PlanStat('🩸', '${plan['target_iron']?.toInt() ?? '-'}mg', l.tr('iron'))),
            Expanded(child: _PlanStat('🦴', '${plan['target_calcium']?.toInt() ?? '-'}mg', l.tr('calcium'))),
          ]),
        ]),
      ),
      const SizedBox(height: 24),

      // Meal sections
      _MealCategory(emoji: '🌅', title: l.tr('breakfast'), color: AppColors.trimester1, meals: List<Map<String, dynamic>>.from(plan['breakfast_meals'] ?? []), onTap: onMealTap),
      _MealCategory(emoji: '☀️', title: l.tr('lunch'), color: AppColors.trimester2, meals: List<Map<String, dynamic>>.from(plan['lunch_meals'] ?? []), onTap: onMealTap),
      _MealCategory(emoji: '🌙', title: l.tr('dinner'), color: AppColors.secondary, meals: List<Map<String, dynamic>>.from(plan['dinner_meals'] ?? []), onTap: onMealTap),
      _MealCategory(emoji: '🍎', title: l.tr('snacks'), color: AppColors.trimester3, meals: List<Map<String, dynamic>>.from(plan['snack_meals'] ?? []), onTap: onMealTap),

      // Dietary alerts
      if ((plan['dietary_alerts'] as List?)?.isNotEmpty == true) ...[
        const SizedBox(height: 20),
        Row(children: [
          Container(width: 32, height: 32, decoration: BoxDecoration(color: AppColors.warning.withValues(alpha: 0.1), shape: BoxShape.circle), child: const Icon(Icons.warning_amber, size: 16, color: AppColors.warning)),
          const SizedBox(width: 10),
          Text(l.tr('dietary_alerts'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.warning)),
        ]),
        const SizedBox(height: 10),
        ...((plan['dietary_alerts'] as List).map((a) => Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: AppColors.warning.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.warning.withValues(alpha: 0.12))),
          child: Text('$a', style: const TextStyle(fontSize: 13, height: 1.4)),
        ))),
      ],
    ]);
  }
}

class _PlanStat extends StatelessWidget {
  final String emoji, value, label;
  const _PlanStat(this.emoji, this.value, this.label);
  @override
  Widget build(BuildContext context) => Column(children: [
    Text(emoji, style: const TextStyle(fontSize: 20)),
    const SizedBox(height: 4),
    Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white)),
    Text(label, style: const TextStyle(fontSize: 11, color: Colors.white70)),
  ]);
}

class _MealCategory extends StatelessWidget {
  final String emoji, title; final Color color;
  final List<Map<String, dynamic>> meals; final Function(String) onTap;
  const _MealCategory({required this.emoji, required this.title, required this.color, required this.meals, required this.onTap});

  @override
  Widget build(BuildContext context) {
    if (meals.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text(emoji, style: const TextStyle(fontSize: 18)),
        const SizedBox(width: 8),
        Text(title, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color)),
      ]),
      const SizedBox(height: 10),
      ...meals.asMap().entries.map((e) => _MealCard(meal: e.value, color: color, onTap: () {
        final id = e.value['id']?.toString() ?? e.value['meal_id']?.toString() ?? '';
        debugPrint('🔍 Meal tap: id="$id", keys=${e.value.keys.toList()}');
        if (id.isNotEmpty) {
          onTap(id);
        } else {
          debugPrint('❌ Empty meal ID! Full data: ${e.value}');
        }
      }, index: e.key)),
      const SizedBox(height: 18),
    ]);
  }
}

class _MealCard extends StatelessWidget {
  final Map<String, dynamic> meal; final Color color; final VoidCallback onTap; final int index;
  const _MealCard({required this.meal, required this.color, required this.onTap, required this.index});

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: Duration(milliseconds: 400 + index * 100),
      curve: Curves.easeOutCubic,
      builder: (_, val, child) => Opacity(
        opacity: val,
        child: Transform.translate(offset: Offset(20 * (1 - val), 0), child: child),
      ),
      child: Card(
        margin: const EdgeInsets.only(bottom: 10),
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        color: Colors.white,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              MealImage(imageUrl: meal['image_url'] as String?, width: 50, height: 50, borderRadius: 15, placeholderColor: color.withValues(alpha: 0.1)),
              const SizedBox(width: 14),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(meal['name'] ?? '', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14), maxLines: 1, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 4),
                Row(children: [
                  Flexible(child: Text('${meal['calories'] ?? '-'} cal', style: TextStyle(fontSize: 12, color: AppColors.textSecondary), overflow: TextOverflow.ellipsis)),
                  Container(width: 4, height: 4, margin: const EdgeInsets.symmetric(horizontal: 6), decoration: BoxDecoration(color: AppColors.textHint, shape: BoxShape.circle)),
                  Flexible(child: Text('${meal['protein_g'] ?? '-'}g ${AppLocalizations.of(context).tr('protein')}', style: TextStyle(fontSize: 12, color: AppColors.textSecondary), overflow: TextOverflow.ellipsis)),
                ]),
              ])),
              const Icon(Icons.chevron_right_rounded, color: AppColors.textHint),
            ]),
          ),
        ),
      ),
    );
  }
}
