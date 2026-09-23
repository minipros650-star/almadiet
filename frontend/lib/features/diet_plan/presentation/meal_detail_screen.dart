import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/widgets/meal_image.dart';
import '../../../core/utils/api_client.dart';
import '../../../core/localization/app_localizations.dart';

class MealDetailScreen extends ConsumerStatefulWidget {
  final String mealId;
  const MealDetailScreen({super.key, required this.mealId});
  @override
  ConsumerState<MealDetailScreen> createState() => _MealDetailScreenState();
}

class _MealDetailScreenState extends ConsumerState<MealDetailScreen> {
  Map<String, dynamic>? _meal;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadMeal();
  }

  Future<void> _loadMeal() async {
    setState(() { _loading = true; });
    try {
      final api = ref.read(apiClientProvider);
      final res = await api.dio.get('/api/v1/meals/${widget.mealId}');
      if (mounted) {
        setState(() { _meal = Map<String, dynamic>.from(res.data); _loading = false; });
      }
    } catch (e) {
      if (mounted) {
        setState(() { _loading = false; });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    if (_loading) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const CircularProgressIndicator(color: AppColors.primary),
          const SizedBox(height: 16),
          Text(l.tr('loading')),
        ])),
      );
    }
    if (_meal == null) {
      return Scaffold(
        appBar: AppBar(title: Text(l.tr('diet'))),
        body: Center(child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.restaurant_rounded, size: 44, color: AppColors.textSecondary),
            const SizedBox(height: 16),
            Text(l.tr('error_generic'), style: const TextStyle(fontSize: 15, height: 1.5), textAlign: TextAlign.center),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _loadMeal,
              icon: const Icon(Icons.refresh_rounded),
              label: Text(l.tr('retry')),
            ),
          ]),
        )),
      );
    }

    final meal = _meal!;
    final allergens = List<String>.from(meal['allergens'] ?? const []);
    final safetyNotes = List<String>.from(meal['food_safety_notes'] ?? const []);
    final cautions = meal['cautions'];
    final ingredients = List<Map<String, dynamic>>.from(meal['ingredients'] ?? const []);

    return Scaffold(
      body: CustomScrollView(slivers: [
        SliverAppBar(
          expandedHeight: 240,
          pinned: true,
          stretch: true,
          flexibleSpace: FlexibleSpaceBar(
            title: Text(AppLocalizations.of(context).mealName(meal), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, shadows: [Shadow(blurRadius: 8, color: Colors.black45)]), maxLines: 1, overflow: TextOverflow.ellipsis),
            background: MealHeroImage(imageUrl: meal['image_url'] as String?, height: 240),
          ),
        ),
        SliverToBoxAdapter(child: ResponsiveCenter(child: Padding(
          padding: Responsive.screenPadding(context).copyWith(top: 20, bottom: 40),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // Tags
            Wrap(spacing: 8, runSpacing: 8, children: [
              if ((meal['region'] ?? '').toString().isNotEmpty)
                _Tag(meal['region'], AppColors.primary, Icons.location_on),
              if ((meal['meal_type'] ?? '').toString().isNotEmpty)
                _Tag(meal['meal_type'], AppColors.secondary, Icons.restaurant),
              if (meal['is_vegetarian'] == true) _Tag(l.tr('veg'), AppColors.success, Icons.eco),
              if (meal['preparation_time_minutes'] != null)
                _Tag('${meal['preparation_time_minutes']} min', AppColors.accent, Icons.schedule),
            ]),
            const SizedBox(height: 24),

            // ── Allergens (prominent, never hidden) ──
            _SectionHeader(icon: Icons.report_rounded, title: l.tr('allergens_section'), color: AppColors.warning),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.warning.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppColors.warning.withValues(alpha: 0.2)),
              ),
              child: allergens.isEmpty
                  ? Text(l.tr('no_known_allergens'), style: const TextStyle(fontSize: 14, height: 1.4))
                  : Wrap(spacing: 8, runSpacing: 8, children: [
                      for (final a in allergens)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(
                            color: AppColors.warning.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Row(mainAxisSize: MainAxisSize.min, children: [
                            Icon(Icons.block_rounded, size: 13, color: AppColors.warning),
                            const SizedBox(width: 5),
                            Text(a, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.warning)),
                          ]),
                        ),
                    ]),
            ),
            const SizedBox(height: 24),

            // ── Nutrition grid ──
            _SectionHeader(icon: Icons.bar_chart_rounded, title: l.tr('nutrition_per_serving'), color: AppColors.primary),
            const SizedBox(height: 12),
            LayoutBuilder(builder: (ctx, constraints) {
              final cols = constraints.maxWidth > 400 ? 4 : 3;
              return GridView.count(
                crossAxisCount: cols, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 0.85,
                children: [
                  _NutriCard('${meal['calories']}', 'kcal', l.tr('calories'), AppColors.trimester1),
                  _NutriCard('${meal['protein_g']}', 'g', l.tr('protein'), AppColors.secondary),
                  _NutriCard('${meal['carbs_g']}', 'g', l.tr('carbs'), AppColors.trimester2),
                  _NutriCard('${meal['fat_g']}', 'g', l.tr('fat'), AppColors.accent),
                  _NutriCard('${meal['iron_mg']}', 'mg', l.tr('iron'), AppColors.error),
                  _NutriCard('${meal['calcium_mg']}', 'mg', l.tr('calcium'), AppColors.info),
                  _NutriCard('${meal['folate_mcg']}', 'mcg', l.tr('folate'), AppColors.trimester3),
                  _NutriCard('${meal['fiber_g']}', 'g', l.tr('fiber'), AppColors.primaryDark),
                ],
              );
            }),
            const SizedBox(height: 24),

            // ── Ingredients ──
            if (ingredients.isNotEmpty) ...[
              _SectionHeader(icon: Icons.spa_rounded, title: l.tr('ingredients'), color: AppColors.secondary),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 10)]),
                child: Column(children: [
                  ...ingredients.map((ing) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Row(children: [
                      Container(width: 8, height: 8, decoration: BoxDecoration(gradient: AppColors.primaryGradient, shape: BoxShape.circle)),
                      const SizedBox(width: 12),
                      Expanded(child: Text('${ing['name']}', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500))),
                      if ((ing['quantity'] ?? '').toString().isNotEmpty)
                        Text('${ing['quantity']}', style: TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                    ]),
                  )),
                ]),
              ),
              const SizedBox(height: 24),
            ],

            // ── Food safety notes ──
            if (safetyNotes.isNotEmpty) ...[
              _SectionHeader(icon: Icons.clean_hands_rounded, title: l.tr('food_safety'), color: AppColors.error),
              const SizedBox(height: 12),
              for (final note in safetyNotes)
                Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(color: AppColors.error.withValues(alpha: 0.05), borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.error.withValues(alpha: 0.12))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(Icons.verified_user_rounded, size: 16, color: AppColors.error),
                    const SizedBox(width: 10),
                    Expanded(child: Text(note, style: const TextStyle(fontSize: 13, height: 1.45))),
                  ]),
                ),
              const SizedBox(height: 16),
            ],

            // ── Cautions ──
            if (cautions != null && cautions.toString().isNotEmpty) ...[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: AppColors.warning.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(16), border: Border.all(color: AppColors.warning.withValues(alpha: 0.12))),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(Icons.warning_amber_rounded, size: 20, color: AppColors.warning),
                  const SizedBox(width: 12),
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(l.tr('cautions'), style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.warning)),
                    const SizedBox(height: 4),
                    Text('$cautions', style: const TextStyle(fontSize: 13, height: 1.4)),
                  ])),
                ]),
              ),
              const SizedBox(height: 16),
            ],

            // ── Provenance: where this information comes from ──
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(color: AppColors.inputFill, borderRadius: BorderRadius.circular(16)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(Icons.fact_check_rounded, size: 16, color: AppColors.textSecondary),
                  const SizedBox(width: 8),
                  Text(l.tr('about_this_info'), style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.textSecondary)),
                ]),
                const SizedBox(height: 8),
                Text(
                  '${l.tr('source')}: ${meal['source'] ?? l.tr('not_documented')}\n'
                  '${l.tr('content_version')}: ${meal['evidence_version'] ?? '-'}\n'
                  '${l.tr('review_status')}: ${meal['content_status'] ?? '-'}',
                  style: TextStyle(fontSize: 12, height: 1.6, color: AppColors.textSecondary),
                ),
              ]),
            ),
          ]),
        ))),
      ]),
    );
  }
}

class _Tag extends StatelessWidget {
  final String text; final Color color; final IconData icon;
  const _Tag(this.text, this.color, this.icon);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
    child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 14, color: color), const SizedBox(width: 4), Text(text, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: color))]),
  );
}

class _SectionHeader extends StatelessWidget {
  final IconData icon; final String title; final Color color;
  const _SectionHeader({required this.icon, required this.title, required this.color});
  @override
  Widget build(BuildContext context) => Row(children: [
    Container(width: 32, height: 32, decoration: BoxDecoration(color: color.withValues(alpha: 0.1), shape: BoxShape.circle), child: Icon(icon, size: 16, color: color)),
    const SizedBox(width: 10),
    Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
  ]);
}

class _NutriCard extends StatelessWidget {
  final String value, unit, label; final Color color;
  const _NutriCard(this.value, this.unit, this.label, this.color);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(10),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(16), border: Border.all(color: color.withValues(alpha: 0.1))),
    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color)),
      Text(unit, style: TextStyle(fontSize: 10, color: color.withValues(alpha: 0.7))),
      Text(label, style: TextStyle(fontSize: 9, color: AppColors.textSecondary), textAlign: TextAlign.center),
    ]),
  );
}
