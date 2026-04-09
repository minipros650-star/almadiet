import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/widgets/loading_animations.dart';
import '../../../core/utils/api_client.dart';
import '../../../core/localization/app_localizations.dart';

class EmergencyScreen extends ConsumerStatefulWidget {
  const EmergencyScreen({super.key});
  @override
  ConsumerState<EmergencyScreen> createState() => _EmergencyScreenState();
}

class _EmergencyScreenState extends ConsumerState<EmergencyScreen> with SingleTickerProviderStateMixin {
  List<Map<String, dynamic>> _emergencies = [];
  bool _loading = true;
  late AnimationController _animCtrl;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 700));
    _loadEmergencies();
  }

  @override
  void dispose() { _animCtrl.dispose(); super.dispose(); }

  Future<void> _loadEmergencies() async {
    try {
      final api = ref.read(apiClientProvider);
      final res = await api.dio.get('/api/emergency/list');
      setState(() { _emergencies = List<Map<String, dynamic>>.from(res.data); _loading = false; });
      _animCtrl.forward();
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l.tr('emergency'))),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showReportDialog,
        backgroundColor: AppColors.error,
        icon: const Icon(Icons.emergency, color: Colors.white),
        label: Text(l.tr('report'), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
        elevation: 4,
      ),
      body: _loading
          ? PregnancyLoader(message: l.tr('loading'))
          : _emergencies.isEmpty
              ? _EmptyState()
              : FadeTransition(
                  opacity: CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut),
                  child: ResponsiveCenter(
                    child: ListView.builder(
                      padding: Responsive.screenPadding(context).copyWith(top: 16, bottom: 80),
                      itemCount: _emergencies.length,
                      itemBuilder: (_, i) => _EmergencyCard(emergency: _emergencies[i], onResolve: () => _resolve(_emergencies[i]['id']), index: i),
                    ),
                  ),
                ),
    );
  }

  void _showReportDialog() {
    final l = AppLocalizations.of(context);
    String type = 'GDM';
    final descCtrl = TextEditingController();
    final types = [
      {'type': 'GDM', 'emoji': '🩸', 'label': l.tr('gestational_diabetes')},
      {'type': 'preeclampsia', 'emoji': '💊', 'label': l.tr('preeclampsia')},
      {'type': 'anemia', 'emoji': '🫀', 'label': l.tr('anemia')},
      {'type': 'bleeding', 'emoji': '🚨', 'label': l.tr('bleeding')},
      {'type': 'hyperemesis', 'emoji': '🤢', 'label': l.tr('severe_nausea')},
    ];

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => StatefulBuilder(builder: (ctx, setBS) => Padding(
        padding: EdgeInsets.fromLTRB(24, 24, 24, MediaQuery.of(ctx).viewInsets.bottom + 24),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Center(child: Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(2)))),
          const SizedBox(height: 20),
          Text(l.tr('report_emergency'), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Text(l.tr('select_type_desc'), style: TextStyle(color: AppColors.textSecondary, fontSize: 14)),
          const SizedBox(height: 20),
          Wrap(spacing: 8, runSpacing: 8, children: types.map((t) => GestureDetector(
            onTap: () => setBS(() => type = t['type']!),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: type == t['type'] ? AppColors.error.withValues(alpha: 0.1) : AppColors.inputFill,
                borderRadius: BorderRadius.circular(14),
                border: type == t['type'] ? Border.all(color: AppColors.error.withValues(alpha: 0.3)) : null,
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [Text(t['emoji']!, style: const TextStyle(fontSize: 16)), const SizedBox(width: 6), Text(t['label']!, style: TextStyle(fontSize: 13, fontWeight: type == t['type'] ? FontWeight.w700 : FontWeight.w500))]),
            ),
          )).toList()),
          const SizedBox(height: 16),
          TextField(controller: descCtrl, maxLines: 3, decoration: InputDecoration(hintText: l.tr('describe_situation'))),
          const SizedBox(height: 20),
          SizedBox(height: 52, child: ElevatedButton(
            onPressed: () async { Navigator.pop(ctx); await _report(type, descCtrl.text); },
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.error, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
            child: Text(l.tr('submit_report')),
          )),
        ]),
      )),
    );
  }

  Future<void> _report(String type, String desc) async {
    try {
      final api = ref.read(apiClientProvider);
      await api.dio.post('/api/emergency/report', data: {'emergency_type': type, 'description': desc});
      await _loadEmergencies();
    } catch (_) {}
  }

  Future<void> _resolve(String id) async {
    try {
      final api = ref.read(apiClientProvider);
      await api.dio.post('/api/emergency/resolve', data: {'emergency_id': id});
      await _loadEmergencies();
    } catch (_) {}
  }
}

class _EmptyState extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      Container(width: 100, height: 100, decoration: BoxDecoration(color: AppColors.success.withValues(alpha: 0.08), shape: BoxShape.circle), child: const Center(child: Text('🛡️', style: TextStyle(fontSize: 44)))),
      const SizedBox(height: 16),
      Text(l.tr('all_clear'), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Text(l.tr('no_emergencies'), style: TextStyle(color: AppColors.textSecondary, height: 1.5), textAlign: TextAlign.center),
    ]));
  }
}

class _EmergencyCard extends StatefulWidget {
  final Map<String, dynamic> emergency; final VoidCallback onResolve; final int index;
  const _EmergencyCard({required this.emergency, required this.onResolve, required this.index});
  @override
  State<_EmergencyCard> createState() => _EmergencyCardState();
}

class _EmergencyCardState extends State<_EmergencyCard> {
  @override
  Widget build(BuildContext context) {
    final e = widget.emergency;
    final isActive = e['is_active'] == true;
    final l = AppLocalizations.of(context);
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: Duration(milliseconds: 400 + widget.index * 100),
      curve: Curves.easeOutCubic,
      builder: (_, v, child) => Opacity(opacity: v, child: Transform.translate(offset: Offset(0, 20 * (1 - v)), child: child)),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(18),
          border: isActive ? Border.all(color: AppColors.error.withValues(alpha: 0.2)) : null,
          boxShadow: [BoxShadow(color: (isActive ? AppColors.error : Colors.black).withValues(alpha: 0.05), blurRadius: 14)],
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(color: isActive ? AppColors.error.withValues(alpha: 0.1) : AppColors.success.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(isActive ? Icons.warning : Icons.check_circle, size: 14, color: isActive ? AppColors.error : AppColors.success),
                const SizedBox(width: 4),
                Text(isActive ? l.tr('active') : l.tr('resolved'), style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: isActive ? AppColors.error : AppColors.success)),
              ]),
            ),
            const Spacer(),
            Flexible(child: Text(e['emergency_type'] ?? '', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15), overflow: TextOverflow.ellipsis)),
          ]),
          if (e['description'] != null) ...[const SizedBox(height: 10), Text(e['description'], style: TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.4))],
          if (isActive) ...[
            const SizedBox(height: 14),
            SizedBox(width: double.infinity, height: 44, child: OutlinedButton.icon(
              onPressed: widget.onResolve,
              icon: const Icon(Icons.check_circle_outline, size: 18),
              label: Text(l.tr('mark_resolved')),
              style: OutlinedButton.styleFrom(foregroundColor: AppColors.success, side: const BorderSide(color: AppColors.success), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
            )),
          ],
        ]),
      ),
    );
  }
}
