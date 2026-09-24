import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/widgets/meal_image.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/diet_provider.dart';
import '../../../providers/profile_provider.dart';

class DietPlanScreen extends ConsumerStatefulWidget {
  const DietPlanScreen({super.key});
  @override
  ConsumerState<DietPlanScreen> createState() => _DietPlanScreenState();
}

class _DietPlanScreenState extends ConsumerState<DietPlanScreen> {
  bool _swapping = false;

  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(dietProvider.notifier).loadPlans());
  }

  Future<void> _swap(Map<String, dynamic> plan, int dayIndex, String slot, String mealId) async {
    final l = AppLocalizations.of(context);
    setState(() => _swapping = true);
    final error = await ref.read(dietProvider.notifier).swapMeal(
      planId: plan['id'].toString(),
      dayIndex: dayIndex,
      slot: slot,
      currentMealId: mealId,
    );
    if (!mounted) return;
    setState(() => _swapping = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(error ?? l.tr('swap_done')),
      backgroundColor: error != null ? AppColors.error : AppColors.success,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final diet = ref.watch(dietProvider);
    final l = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l.tr('diet_plan'))),
      body: diet.isLoading
          ? Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              const CircularProgressIndicator(color: AppColors.primary),
              const SizedBox(height: 16),
              Text(l.tr('loading_meal_plan')),
            ]))
          : _body(context, diet, l),
    );
  }

  Widget _body(BuildContext context, DietState diet, AppLocalizations l) {
    // Mandated distinct states for personalized suggestions.
    if (diet.blockingCode != null && diet.currentPlan == null) {
      switch (diet.blockingCode) {
        case SuggestionBlock.profileIncomplete:
          return _BlockedView(
            icon: Icons.person_off_outlined,
            title: l.tr('profile_incomplete_title'),
            message: l.tr('profile_incomplete_msg'),
            actionLabel: l.tr('complete_profile'),
            onAction: () => context.go('/profile-completion'),
          );
        case SuggestionBlock.clinicianReview:
        case SuggestionBlock.needsClinicianReview:
          // NEEDS_CLINICIAN_REVIEW = no clinician-approved ACTIVE policy
          // exists; same safe state: defer to a human clinician.
          return _BlockedView(
            icon: Icons.medical_services_outlined,
            title: l.tr('clinician_review_title'),
            message: l.tr('clinician_review_msg'),
          );
        case SuggestionBlock.noSafeSuggestion:
          return _BlockedView(
            icon: Icons.no_meals_outlined,
            title: l.tr('no_safe_suggestion_title'),
            message: diet.error ?? l.tr('no_safe_suggestion_msg'),
          );
        case SuggestionBlock.consentRequired:
          return _BlockedView(
            icon: Icons.privacy_tip_outlined,
            title: l.tr('consent_title'),
            message: l.tr('consent_required_diet_msg'),
            actionLabel: l.tr('review_consent'),
            onAction: () => context.go('/consent'),
          );
      }
    }
    if (diet.error != null && diet.currentPlan == null) {
      return _ErrorView(message: diet.error!);
    }
    if (diet.currentPlan == null) {
      return _EmptyState();
    }
    return _PlanView(
      plan: diet.currentPlan!,
      selectedDay: diet.selectedDayIndex,
      swapping: _swapping,
      onDaySelected: (d) => ref.read(dietProvider.notifier).selectDay(d),
      onMealTap: (id) {
        if (id.isNotEmpty && context.mounted) GoRouter.of(context).push('/meal/$id');
      },
      onSwap: _swap,
    );
  }
}

/// Distinct state views for profile/clinician/no-safe/consent blocks.
class _BlockedView extends StatelessWidget {
  final IconData icon;
  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

  const _BlockedView({
    required this.icon,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Center(child: ResponsiveCenter(child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Container(
          width: 88, height: 88,
          decoration: BoxDecoration(
            color: AppColors.primary.withValues(alpha: 0.08), shape: BoxShape.circle),
          child: Icon(icon, size: 40, color: AppColors.primary),
        ),
        const SizedBox(height: 20),
        Text(title, textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        Text(message,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 14, height: 1.5, color: AppColors.textSecondary)),
        if (actionLabel != null && onAction != null) ...[
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: onAction,
            icon: const Icon(Icons.arrow_forward_rounded),
            label: Text(actionLabel!),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            ),
          ),
        ],
      ]),
    )));
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

class _ErrorView extends ConsumerWidget {
  final String message;
  const _ErrorView({required this.message});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = AppLocalizations.of(context);
    return Center(child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Icon(Icons.cloud_off_rounded, size: 48, color: AppColors.textSecondary),
        const SizedBox(height: 16),
        Text(message, textAlign: TextAlign.center, style: const TextStyle(fontSize: 15, height: 1.5)),
        const SizedBox(height: 20),
        ElevatedButton.icon(
          onPressed: () => ref.read(dietProvider.notifier).loadPlans(),
          icon: const Icon(Icons.refresh_rounded),
          label: Text(l.tr('retry')),
        ),
      ]),
    ));
  }
}

class _PlanView extends StatelessWidget {
  final Map<String, dynamic> plan;
  final int selectedDay;
  final bool swapping;
  final Function(int) onDaySelected;
  final Function(String) onMealTap;
  final Future<void> Function(Map<String, dynamic>, int, String, String) onSwap;

  const _PlanView({
    required this.plan,
    required this.selectedDay,
    required this.swapping,
    required this.onDaySelected,
    required this.onMealTap,
    required this.onSwap,
  });

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final days = List<Map<String, dynamic>>.from(plan['days'] ?? []);
    final day = days.firstWhere(
      (d) => d['day_index'] == selectedDay,
      orElse: () => days.isNotEmpty ? days.first : <String, dynamic>{'meals': {}},
    );
    final meals = Map<String, dynamic>.from(day['meals'] ?? {});
    final alerts = List<String>.from(plan['dietary_alerts'] ?? []);

    // Calendar dates for the plan window (plan_start → plan_start+6).
    // Day N of the plan == plan_start + (N-1) days.
    final planStart = DateTime.tryParse('${plan['plan_start'] ?? ''}');
    String? dateLabelFor(int dayIndex) {
      if (planStart == null) return null;
      final d = planStart.add(Duration(days: dayIndex - 1));
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      final wd = weekdays[d.weekday - 1];
      return '$wd, ${d.day} ${months[d.month - 1]}';
    }
    final today = DateTime.now();
    final todayDate = DateTime(today.year, today.month, today.day);
    int? todayPlanDay;
    if (planStart != null) {
      final start = DateTime(planStart.year, planStart.month, planStart.day);
      final diff = todayDate.difference(start).inDays;
      if (diff >= 0 && diff <= 6) todayPlanDay = diff + 1;
    }

    return ListView(padding: Responsive.screenPadding(context).copyWith(top: 16, bottom: 32), children: [
      // Reference values header — explicitly informational.
      Container(
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(gradient: AppColors.primaryGradient, borderRadius: BorderRadius.circular(22), boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.25), blurRadius: 16, offset: const Offset(0, 6))]),
        child: Column(children: [
          Text(l.tr('daily_targets'), style: const TextStyle(fontSize: 13, color: Colors.white70)),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: _PlanStat('${plan['target_calories']?.toInt() ?? '-'}', l.tr('calories'))),
            Expanded(child: _PlanStat('${plan['target_protein']?.toInt() ?? '-'}g', l.tr('protein'))),
            Expanded(child: _PlanStat('${plan['target_iron']?.toInt() ?? '-'}mg', l.tr('iron'))),
            Expanded(child: _PlanStat('${plan['target_calcium']?.toInt() ?? '-'}mg', l.tr('calcium'))),
          ]),
        ]),
      ),
      const SizedBox(height: 12),
      // Trimester/week + non-prescription note.
      Row(children: [
        Icon(Icons.info_outline_rounded, size: 14, color: AppColors.textSecondary),
        const SizedBox(width: 6),
        Expanded(child: Text(l.tr('reference_only'), style: TextStyle(fontSize: 12, color: AppColors.textSecondary))),
      ]),
      const SizedBox(height: 10),
      // Mandated transparency lines for personalized suggestions.
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.secondary.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(Icons.auto_awesome_outlined, size: 14, color: AppColors.textSecondary),
            const SizedBox(width: 6),
            Expanded(child: Text(l.tr('suggested_based_on'), style: TextStyle(fontSize: 12, color: AppColors.textSecondary))),
          ]),
          const SizedBox(height: 4),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(Icons.filter_alt_outlined, size: 14, color: AppColors.textSecondary),
            const SizedBox(width: 6),
            Expanded(child: Text(l.tr('filtered_using'), style: TextStyle(fontSize: 12, color: AppColors.textSecondary))),
          ]),
        ]),
      ),
      const SizedBox(height: 16),

      // ── Day selector (7 calendar days) ──
      SizedBox(
        height: 60,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: days.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (ctx, i) {
            final dayIndex = days[i]['day_index'] as int;
            final selected = dayIndex == selectedDay;
            final isToday = dayIndex == todayPlanDay;
            final dateLabel = dateLabelFor(dayIndex);
            return GestureDetector(
              onTap: () => onDaySelected(dayIndex),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: selected ? AppColors.primary : AppColors.inputFill,
                  borderRadius: BorderRadius.circular(14),
                  border: isToday && !selected
                      ? Border.all(color: AppColors.primary.withValues(alpha: 0.5), width: 1.2)
                      : null,
                ),
                child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.calendar_today_rounded, size: 12, color: selected ? Colors.white : AppColors.textSecondary),
                    const SizedBox(width: 4),
                    Text('${l.tr('day')} $dayIndex', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: selected ? Colors.white : AppColors.textPrimary)),
                    if (isToday) ...[
                      const SizedBox(width: 5),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                        decoration: BoxDecoration(
                          color: selected ? Colors.white24 : AppColors.primary.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(l.tr('today_badge'), style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.w700, color: selected ? Colors.white : AppColors.primary)),
                      ),
                    ],
                  ]),
                  if (dateLabel != null)
                    Text(dateLabel, style: TextStyle(fontSize: 10, color: selected ? Colors.white70 : AppColors.textSecondary)),
                ]),
              ),
            );
          },
        ),
      ),
      const SizedBox(height: 18),

      // ── Slots of the selected day ──
      _SlotSection(
        title: l.tr('breakfast'),
        slot: 'breakfast',
        color: AppColors.trimester1,
        cards: List<Map<String, dynamic>>.from(meals['breakfast'] ?? []),
        onTap: onMealTap,
        onSwap: (mealId) => onSwap(plan, selectedDay, 'breakfast', mealId),
        swapping: swapping,
      ),
      _SlotSection(
        title: l.tr('lunch'),
        slot: 'lunch',
        color: AppColors.trimester2,
        cards: List<Map<String, dynamic>>.from(meals['lunch'] ?? []),
        onTap: onMealTap,
        onSwap: (mealId) => onSwap(plan, selectedDay, 'lunch', mealId),
        swapping: swapping,
      ),
      _SlotSection(
        title: l.tr('snacks'),
        slot: 'snack',
        color: AppColors.trimester3,
        cards: List<Map<String, dynamic>>.from(meals['snack'] ?? []),
        onTap: onMealTap,
        onSwap: (mealId) => onSwap(plan, selectedDay, 'snack', mealId),
        swapping: swapping,
      ),
      _SlotSection(
        title: l.tr('dinner'),
        slot: 'dinner',
        color: AppColors.secondary,
        cards: List<Map<String, dynamic>>.from(meals['dinner'] ?? []),
        onTap: onMealTap,
        onSwap: (mealId) => onSwap(plan, selectedDay, 'dinner', mealId),
        swapping: swapping,
      ),

      // ── Safety notes ──
      if (alerts.isNotEmpty) ...[
        const SizedBox(height: 20),
        Row(children: [
          Container(width: 32, height: 32, decoration: BoxDecoration(color: AppColors.warning.withValues(alpha: 0.1), shape: BoxShape.circle), child: const Icon(Icons.health_and_safety_rounded, size: 16, color: AppColors.warning)),
          const SizedBox(width: 10),
          Text(l.tr('dietary_alerts'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.warning)),
        ]),
        const SizedBox(height: 10),
        ...alerts.map((a) => Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: AppColors.warning.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.warning.withValues(alpha: 0.12))),
          child: Text(a, style: const TextStyle(fontSize: 13, height: 1.4)),
        )),
      ],
    ]);
  }
}

class _SlotSection extends StatelessWidget {
  final String title, slot;
  final Color color;
  final List<Map<String, dynamic>> cards;
  final Function(String) onTap;
  final Function(String) onSwap;
  final bool swapping;

  const _SlotSection({
    required this.title,
    required this.slot,
    required this.color,
    required this.cards,
    required this.onTap,
    required this.onSwap,
    required this.swapping,
  });

  @override
  Widget build(BuildContext context) {
    if (cards.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color)),
      const SizedBox(height: 10),
      ...cards.map((meal) {
        final id = meal['id']?.toString() ?? '';
        final why = List<String>.from(meal['why_suggested'] ?? []);
        return Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(18),
            boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 10)],
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: id.isNotEmpty ? () => onTap(id) : null,
              child: Row(children: [
                MealImage(imageUrl: meal['image_url'] as String?, width: 52, height: 52, borderRadius: 15, placeholderColor: color.withValues(alpha: 0.1)),
                const SizedBox(width: 14),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(AppLocalizations.of(context).mealName(meal), style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14), maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 4),
                  Row(children: [
                    Flexible(child: Text('${meal['calories'] ?? '-'} ${AppLocalizations.of(context).tr('calories')}', style: TextStyle(fontSize: 12, color: AppColors.textSecondary), overflow: TextOverflow.ellipsis)),
                    Container(width: 4, height: 4, margin: const EdgeInsets.symmetric(horizontal: 6), decoration: BoxDecoration(color: AppColors.textHint, shape: BoxShape.circle)),
                    Flexible(child: Text('${meal['protein_g'] ?? '-'}g ${AppLocalizations.of(context).tr('protein')}', style: TextStyle(fontSize: 12, color: AppColors.textSecondary), overflow: TextOverflow.ellipsis)),
                  ]),
                ])),
                const Icon(Icons.chevron_right_rounded, color: AppColors.textHint),
              ]),
            ),
            if (why.isNotEmpty) ...[
              const SizedBox(height: 10),
              // "Why suggested" chips — honest preference/review reasons only.
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final w in why)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withValues(alpha: 0.07),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        Icon(Icons.lightbulb_outline_rounded, size: 12, color: AppColors.primary),
                        const SizedBox(width: 4),
                        Flexible(
                          child: Text(w,
                              style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                              overflow: TextOverflow.ellipsis),
                        ),
                      ]),
                    ),
                ],
              ),
            ],
            const SizedBox(height: 10),
            SizedBox(
              height: 36,
              child: OutlinedButton.icon(
                onPressed: swapping ? null : () => onSwap(id),
                icon: Icon(Icons.swap_horiz_rounded, size: 16),
                label: Text(AppLocalizations.of(context).tr('swap_meal'), style: const TextStyle(fontSize: 12)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.primary,
                  side: BorderSide(color: AppColors.primary.withValues(alpha: 0.4)),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                ),
              ),
            ),
          ]),
        );
      }),
      const SizedBox(height: 12),
    ]);
  }
}

class _PlanStat extends StatelessWidget {
  final String value, label;
  const _PlanStat(this.value, this.label);
  @override
  Widget build(BuildContext context) => Column(children: [
    Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white)),
    Text(label, style: const TextStyle(fontSize: 11, color: Colors.white70)),
  ]);
}
