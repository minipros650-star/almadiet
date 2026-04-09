import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/data/healthy_tips.dart';
import '../../../core/widgets/loading_animations.dart';
import '../../../core/widgets/meal_image.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/auth_provider.dart';
import '../../../providers/health_provider.dart';
import '../../../providers/diet_provider.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> with TickerProviderStateMixin {
  late AnimationController _greetCtrl;
  late AnimationController _cardsCtrl;
  late Animation<double> _greetFade;

  @override
  void initState() {
    super.initState();
    _greetCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 700))..forward();
    _cardsCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));
    _greetFade = CurvedAnimation(parent: _greetCtrl, curve: Curves.easeOutCubic);

    Future.delayed(const Duration(milliseconds: 300), () => _cardsCtrl.forward());

    Future.microtask(() {
      ref.read(healthProvider.notifier).loadRecords();
      ref.read(dietProvider.notifier).loadPlans();
    });
  }

  @override
  void dispose() { _greetCtrl.dispose(); _cardsCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authStateProvider);
    final health = ref.watch(healthProvider);
    final diet = ref.watch(dietProvider);
    final userName = auth.user?['name'] ?? 'Mom';
    final tip = HealthyTips.dailyTip();
    final pad = Responsive.screenPadding(context);
    final l = AppLocalizations.of(context);

    if (health.isLoading && diet.isLoading) {
      return Scaffold(body: PregnancyLoader(message: l.tr('loading_dashboard')));
    }

    return Scaffold(
      body: SafeArea(
        child: ResponsiveCenter(
          maxWidth: 700,
          child: RefreshIndicator(
            color: AppColors.primary,
            onRefresh: () async {
              await ref.read(healthProvider.notifier).loadRecords();
              await ref.read(dietProvider.notifier).loadPlans();
            },
            child: ListView(
              padding: pad.copyWith(top: 20, bottom: 24),
              children: [
                // ── Greeting with animated wave ──
                FadeTransition(
                  opacity: _greetFade,
                  child: SlideTransition(
                    position: Tween<Offset>(begin: const Offset(0, -0.1), end: Offset.zero).animate(_greetFade),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Expanded(child: Text('${l.tr('hello')}, $userName! 🌸', style: TextStyle(fontSize: 26 * Responsive.fontScale(context), fontWeight: FontWeight.w700, color: AppColors.textPrimary))),
                        Container(
                          width: 48, height: 48,
                          decoration: BoxDecoration(
                            gradient: AppColors.primaryGradient,
                            shape: BoxShape.circle,
                            boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.2), blurRadius: 12)],
                          ),
                          child: Center(child: Text((userName)[0].toUpperCase(), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 20))),
                        ),
                      ]),
                      const SizedBox(height: 4),
                      Text(l.tr('companion'), style: TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                    ]),
                  ),
                ),
                const SizedBox(height: 20),

                // ── Daily Healthy Tip ──
                _buildAnimated(0, _TipCard(tip: tip)),
                const SizedBox(height: 20),

                // ── Quick Actions ──
                _buildAnimated(1, _QuickActions()),
                const SizedBox(height: 24),

                // ── Health Summary ──
                if (health.latestRecord != null) ...[
                  _buildAnimated(2, Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(l.tr('latest_health'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 12),
                    _HealthSummaryCard(record: health.latestRecord!),
                  ])),
                  const SizedBox(height: 24),
                ],

                // ── Current Diet Plan or CTA ──
                _buildAnimated(3, diet.currentPlan != null
                    ? _DietPreview(plan: diet.currentPlan!, onMealTap: (id) {
                        if (id.isNotEmpty && context.mounted) {
                          debugPrint('🚀 Navigating to /meal/$id');
                          GoRouter.of(context).push('/meal/$id');
                        }
                      })
                    : _NoPlanCta()),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAnimated(int index, Widget child) {
    return AnimatedBuilder(
      animation: _cardsCtrl,
      builder: (_, _) {
        final delay = (index * 0.15).clamp(0.0, 0.6);
        final progress = ((_cardsCtrl.value - delay) / (1 - delay)).clamp(0.0, 1.0);
        final curved = Curves.easeOutCubic.transform(progress);
        return Opacity(
          opacity: curved,
          child: Transform.translate(offset: Offset(0, 40 * (1 - curved)), child: child),
        );
      },
    );
  }
}

// ── Daily Healthy Tip Card ──
class _TipCard extends StatelessWidget {
  final Map<String, String> tip;
  const _TipCard({required this.tip});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.primary.withValues(alpha: 0.08), AppColors.secondary.withValues(alpha: 0.06)],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.12)),
      ),
      child: Row(children: [
        Text(tip['emoji'] ?? '💡', style: const TextStyle(fontSize: 28)),
        const SizedBox(width: 14),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(l.tr('daily_tip'), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.primary)),
          const SizedBox(height: 4),
          Text(tip['tip'] ?? '', style: const TextStyle(fontSize: 13, height: 1.4, color: AppColors.textPrimary)),
        ])),
      ]),
    );
  }
}

// ── Quick Action Cards ──
class _QuickActions extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Row(children: [
      Expanded(child: _ActionCard(icon: Icons.monitor_heart_outlined, label: l.tr('health_input_label'), color: AppColors.primary, onTap: () => context.push('/health-input'))),
      const SizedBox(width: 12),
      Expanded(child: _ActionCard(icon: Icons.restaurant_menu_rounded, label: l.tr('my_diet_plan'), color: AppColors.secondary, onTap: () => context.go('/diet'))),
      const SizedBox(width: 12),
      Expanded(child: _ActionCard(icon: Icons.emergency_rounded, label: l.tr('emergency_help'), color: AppColors.accent, onTap: () => context.go('/emergency'))),
    ]);
  }
}

class _ActionCard extends StatefulWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _ActionCard({required this.icon, required this.label, required this.color, required this.onTap});
  @override
  State<_ActionCard> createState() => _ActionCardState();
}

class _ActionCardState extends State<_ActionCard> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) { setState(() => _pressed = false); widget.onTap(); },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: _pressed ? 0.93 : 1.0,
        duration: const Duration(milliseconds: 150),
        curve: Curves.easeOut,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 22),
          decoration: BoxDecoration(
            color: widget.color.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: widget.color.withValues(alpha: 0.12)),
            boxShadow: [BoxShadow(color: widget.color.withValues(alpha: 0.06), blurRadius: 12, offset: const Offset(0, 4))],
          ),
          child: Column(children: [
            Container(
              width: 48, height: 48,
              decoration: BoxDecoration(color: widget.color.withValues(alpha: 0.15), shape: BoxShape.circle),
              child: Icon(widget.icon, size: 24, color: widget.color),
            ),
            const SizedBox(height: 10),
            Text(widget.label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: widget.color), textAlign: TextAlign.center),
          ]),
        ),
      ),
    );
  }
}

// ── Health Summary Card ──
class _HealthSummaryCard extends StatelessWidget {
  final Map<String, dynamic> record;
  const _HealthSummaryCard({required this.record});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.06), blurRadius: 20, offset: const Offset(0, 6))],
      ),
      child: Column(children: [
        Row(children: [
          _Chip('T${record['trimester']}', AppColors.primary),
          const SizedBox(width: 8),
          _Chip('${AppLocalizations.of(context).tr('week')} ${record['week_number']}', AppColors.secondary),
          const Spacer(),
          Icon(Icons.chevron_right, color: AppColors.textHint, size: 20),
        ]),
        const SizedBox(height: 18),
        Row(children: [
          Expanded(child: _Stat(label: AppLocalizations.of(context).tr('weight'), value: '${record['current_weight_kg']}', unit: 'kg', icon: Icons.monitor_weight_outlined, color: AppColors.primary)),
          Expanded(child: _Stat(label: 'Hb', value: '${record['hemoglobin']}', unit: 'g/dL', icon: Icons.bloodtype_outlined, color: AppColors.error)),
          Expanded(child: _Stat(label: 'BP', value: '${record['blood_pressure_sys']?.toInt() ?? '-'}/${record['blood_pressure_dia']?.toInt() ?? '-'}', unit: 'mmHg', icon: Icons.favorite_outline, color: AppColors.accent)),
        ]),
      ]),
    );
  }
}

class _Chip extends StatelessWidget {
  final String text; final Color color;
  const _Chip(this.text, this.color);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
    child: Text(text, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
  );
}

class _Stat extends StatelessWidget {
  final String label, value, unit; final IconData icon; final Color color;
  const _Stat({required this.label, required this.value, required this.unit, required this.icon, required this.color});
  @override
  Widget build(BuildContext context) => Column(children: [
    Container(
      width: 40, height: 40,
      decoration: BoxDecoration(color: color.withValues(alpha: 0.1), shape: BoxShape.circle),
      child: Icon(icon, size: 20, color: color),
    ),
    const SizedBox(height: 8),
    Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
    Text(unit, style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
    Text(label, style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
  ]);
}

// ── Diet Plan Preview ──
class _DietPreview extends StatelessWidget {
  final Map<String, dynamic> plan;
  final Function(String) onMealTap;
  const _DietPreview({required this.plan, required this.onMealTap});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(l.tr('todays_meals'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
      const SizedBox(height: 12),
      _MealSection(title: '🌅 ${l.tr('breakfast')}', meals: List<Map<String, dynamic>>.from(plan['breakfast_meals'] ?? []), onTap: onMealTap),
      _MealSection(title: '☀️ ${l.tr('lunch')}', meals: List<Map<String, dynamic>>.from(plan['lunch_meals'] ?? []), onTap: onMealTap),
      _MealSection(title: '🌙 ${l.tr('dinner')}', meals: List<Map<String, dynamic>>.from(plan['dinner_meals'] ?? []), onTap: onMealTap),
      _MealSection(title: '🍎 ${l.tr('snacks')}', meals: List<Map<String, dynamic>>.from(plan['snack_meals'] ?? []), onTap: onMealTap),
    ]);
  }
}

class _MealSection extends StatelessWidget {
  final String title; final List<Map<String, dynamic>> meals; final Function(String) onTap;
  const _MealSection({required this.title, required this.meals, required this.onTap});
  @override
  Widget build(BuildContext context) {
    if (meals.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      const SizedBox(height: 6),
      ...meals.map((m) => _MealTile(meal: m, onTap: () {
        final id = m['id']?.toString() ?? m['meal_id']?.toString() ?? '';
        debugPrint('🔍 HOME Meal tap: id="$id" name="${m['name']}" keys=${m.keys.toList()}');
        if (id.isNotEmpty) {
          onTap(id);
        } else {
          debugPrint('❌ Empty meal ID! Full meal data: $m');
        }
      })),
      const SizedBox(height: 12),
    ]);
  }
}

class _MealTile extends StatelessWidget {
  final Map<String, dynamic> meal; final VoidCallback onTap;
  const _MealTile({required this.meal, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () {
          debugPrint('🔍 MEAL TAPPED: ${meal['name']} id=${meal['id']}');
          onTap();
        },
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 10, offset: const Offset(0, 3))],
          ),
          child: Row(children: [
            MealImage(imageUrl: meal['image_url'] as String?, width: 44, height: 44, borderRadius: 13),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(meal['name'] ?? 'Meal', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600), maxLines: 1, overflow: TextOverflow.ellipsis),
              Text('${meal['calories'] ?? '-'} cal  •  ${meal['region'] ?? ''}', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
            ])),
            const Icon(Icons.chevron_right, color: AppColors.textHint, size: 20),
          ]),
        ),
      ),
      ),
    );
  }
}

// ── No Plan CTA ──
class _NoPlanCta extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(gradient: AppColors.calmGradient, borderRadius: BorderRadius.circular(24)),
      child: Column(children: [
        const Icon(Icons.restaurant_rounded, size: 52, color: Colors.white),
        const SizedBox(height: 14),
        Text(l.tr('no_plan_yet'), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: Colors.white)),
        const SizedBox(height: 8),
        Text(l.tr('no_plan_desc'), style: const TextStyle(color: Colors.white70, height: 1.4), textAlign: TextAlign.center),
        const SizedBox(height: 20),
        ElevatedButton(
          onPressed: () => context.push('/health-input'),
          style: ElevatedButton.styleFrom(backgroundColor: Colors.white, foregroundColor: AppColors.secondary, padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14)),
          child: Text(l.tr('start_now')),
        ),
      ]),
    );
  }
}
