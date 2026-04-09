import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/widgets/loading_animations.dart';
import '../../../core/widgets/meal_image.dart';
import '../../../core/utils/api_client.dart';
import '../../../core/localization/app_localizations.dart';

class MealDetailScreen extends ConsumerStatefulWidget {
  final String mealId;
  const MealDetailScreen({super.key, required this.mealId});
  @override
  ConsumerState<MealDetailScreen> createState() => _MealDetailScreenState();
}

class _MealDetailScreenState extends ConsumerState<MealDetailScreen> with SingleTickerProviderStateMixin {
  Map<String, dynamic>? _meal;
  bool _loading = true;
  String? _error;
  late AnimationController _animCtrl;

  @override
  void initState() {
    super.initState();
    debugPrint('🍽️ MealDetailScreen opened with mealId: ${widget.mealId}');
    _animCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 700));
    _loadMeal();
  }

  @override
  void dispose() { _animCtrl.dispose(); super.dispose(); }

  Future<void> _loadMeal() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = ref.read(apiClientProvider);
      debugPrint('🌐 Fetching /api/meals/${widget.mealId}');
      final res = await api.dio.get('/api/meals/${widget.mealId}');
      debugPrint('✅ Meal loaded: ${res.data?['name']}');
      if (mounted) {
        setState(() { _meal = Map<String, dynamic>.from(res.data); _loading = false; });
        _animCtrl.forward();
      }
    } catch (e) {
      debugPrint('❌ Failed to load meal ${widget.mealId}: $e');
      if (mounted) {
        setState(() { _loading = false; _error = e.toString(); });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: PregnancyLoader(message: 'Loading meal details...'));
    if (_meal == null) {
      return Scaffold(
      appBar: AppBar(title: const Text('Meal Details')),
      body: Center(child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('😔', style: TextStyle(fontSize: 48)),
          const SizedBox(height: 16),
          const Text('Could not load meal', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: TextStyle(fontSize: 12, color: AppColors.textSecondary), textAlign: TextAlign.center),
          ],
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: _loadMeal,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
          ),
        ]),
      )),
    );
    }

    return Scaffold(
      body: CustomScrollView(slivers: [
        SliverAppBar(
          expandedHeight: 260,
          pinned: true,
          stretch: true,
          flexibleSpace: FlexibleSpaceBar(
            title: Text(AppLocalizations.of(context).mealName(_meal!), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, shadows: [Shadow(blurRadius: 8, color: Colors.black45)]), maxLines: 1, overflow: TextOverflow.ellipsis),
            background: MealHeroImage(
              imageUrl: _meal!['image_url'] as String?,
              height: 260,
            ),
          ),
        ),
        SliverToBoxAdapter(child: FadeTransition(
          opacity: CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut),
          child: ResponsiveCenter(child: Padding(
            padding: Responsive.screenPadding(context).copyWith(top: 20, bottom: 40),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Tags
              Wrap(spacing: 8, runSpacing: 8, children: [
                _Tag(_meal!['region'] ?? '', AppColors.primary, Icons.location_on),
                _Tag(_meal!['meal_type'] ?? '', AppColors.secondary, Icons.restaurant),
                if (_meal!['is_vegetarian'] == true) _Tag('Veg', AppColors.success, Icons.eco),
                if (_meal!['best_time_to_eat'] != null) _Tag(_meal!['best_time_to_eat'], AppColors.accent, Icons.schedule),
              ]),
              const SizedBox(height: 24),

              // Nutrition Grid
              _SectionHeader(emoji: '📊', title: 'Nutrition per Serving'),
              const SizedBox(height: 12),
              LayoutBuilder(builder: (ctx, constraints) {
                final cols = constraints.maxWidth > 400 ? 4 : 3;
                return GridView.count(
                  crossAxisCount: cols, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
                  mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 0.85,
                  children: [
                    _NutriCard('🔥', '${_meal!['calories']}', 'kcal', 'Calories', AppColors.trimester1),
                    _NutriCard('💪', '${_meal!['protein_g']}', 'g', 'Protein', AppColors.secondary),
                    _NutriCard('🍞', '${_meal!['carbs_g']}', 'g', 'Carbs', AppColors.trimester2),
                    _NutriCard('🧈', '${_meal!['fat_g']}', 'g', 'Fat', AppColors.accent),
                    _NutriCard('🩸', '${_meal!['iron_mg']}', 'mg', 'Iron', AppColors.error),
                    _NutriCard('🦴', '${_meal!['calcium_mg']}', 'mg', 'Calcium', AppColors.info),
                    _NutriCard('🧬', '${_meal!['folate_mcg']}', 'mcg', 'Folate', AppColors.trimester3),
                    _NutriCard('🌾', '${_meal!['fiber_g']}', 'g', 'Fiber', AppColors.primaryDark),
                  ],
                );
              }),
              const SizedBox(height: 24),

              // Ingredients
              if (_meal!['ingredients'] != null && (_meal!['ingredients'] as List).isNotEmpty) ...[
                _SectionHeader(emoji: '🥗', title: 'Ingredients'),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 10)]),
                  child: Column(children: [
                    ...(_meal!['ingredients'] as List).map((ing) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Row(children: [
                        Container(width: 8, height: 8, decoration: BoxDecoration(gradient: AppColors.primaryGradient, shape: BoxShape.circle)),
                        const SizedBox(width: 12),
                        Expanded(child: Text('${ing['name']}', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500))),
                        Text('${ing['quantity']}', style: TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                      ]),
                    )),
                  ]),
                ),
                const SizedBox(height: 24),
              ],

              // Benefits
              if (_meal!['benefits'] != null && (_meal!['benefits'] as List).isNotEmpty) ...[
                _SectionHeader(emoji: '✨', title: 'Benefits'),
                const SizedBox(height: 12),
                ...(_meal!['benefits'] as List).asMap().entries.map((e) => TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: 1),
                  duration: Duration(milliseconds: 400 + e.key * 100),
                  curve: Curves.easeOutCubic,
                  builder: (_, v, child) => Opacity(opacity: v, child: Transform.translate(offset: Offset(20 * (1 - v), 0), child: child)),
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(color: AppColors.success.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.success.withValues(alpha: 0.1))),
                    child: Row(children: [const Icon(Icons.check_circle, size: 18, color: AppColors.success), const SizedBox(width: 10), Expanded(child: Text('${e.value}', style: const TextStyle(fontSize: 13, height: 1.4)))]),
                  ),
                )),
                const SizedBox(height: 24),
              ],

              // WHO alignment
              if (_meal!['who_alignment'] != null) ...[
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(color: AppColors.info.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(16), border: Border.all(color: AppColors.info.withValues(alpha: 0.12))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('🏥', style: TextStyle(fontSize: 20)),
                    const SizedBox(width: 12),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('WHO Alignment', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.info)),
                      const SizedBox(height: 4),
                      Text('${_meal!['who_alignment']}', style: const TextStyle(fontSize: 13, height: 1.4)),
                    ])),
                  ]),
                ),
                const SizedBox(height: 16),
              ],

              // Cautions
              if (_meal!['cautions'] != null && _meal!['cautions'].toString().isNotEmpty) ...[
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(color: AppColors.warning.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(16), border: Border.all(color: AppColors.warning.withValues(alpha: 0.12))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('⚠️', style: TextStyle(fontSize: 20)),
                    const SizedBox(width: 12),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('Cautions', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.warning)),
                      const SizedBox(height: 4),
                      Text('${_meal!['cautions']}', style: const TextStyle(fontSize: 13, height: 1.4)),
                    ])),
                  ]),
                ),
              ],
            ]),
          )),
        )),
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
  final String emoji, title;
  const _SectionHeader({required this.emoji, required this.title});
  @override
  Widget build(BuildContext context) => Row(children: [Text(emoji, style: const TextStyle(fontSize: 20)), const SizedBox(width: 8), Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700))]);
}

class _NutriCard extends StatelessWidget {
  final String emoji, value, unit, label; final Color color;
  const _NutriCard(this.emoji, this.value, this.unit, this.label, this.color);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(10),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(16), border: Border.all(color: color.withValues(alpha: 0.1))),
    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      Text(emoji, style: const TextStyle(fontSize: 16)),
      const SizedBox(height: 2),
      Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color)),
      Text(unit, style: TextStyle(fontSize: 10, color: color.withValues(alpha: 0.7))),
      Text(label, style: TextStyle(fontSize: 9, color: AppColors.textSecondary)),
    ]),
  );
}
