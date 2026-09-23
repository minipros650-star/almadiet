import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/utils/api_client.dart';
import '../../../core/localization/app_localizations.dart';

/// Urgent Help — safety information only.
///
/// This screen can never assess, diagnose, treat, or resolve anything.
/// It shows reviewed warning signs, regional emergency contacts, and lets
/// the user record observations to share with a clinician.
class UrgentHelpScreen extends ConsumerStatefulWidget {
  const UrgentHelpScreen({super.key});
  @override
  ConsumerState<UrgentHelpScreen> createState() => _UrgentHelpScreenState();
}

class _UrgentHelpScreenState extends ConsumerState<UrgentHelpScreen> {
  Map<String, dynamic>? _info;
  List<Map<String, dynamic>> _notes = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = ref.read(apiClientProvider);
      final infoRes = await api.dio.get('/api/v1/urgent/info');
      final notesRes = await api.dio.get('/api/v1/urgent/notes');
      if (!mounted) return;
      setState(() {
        _info = Map<String, dynamic>.from(infoRes.data);
        _notes = List<Map<String, dynamic>>.from(notesRes.data);
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load safety information. Check your connection and try again.';
      });
    }
  }

  Future<void> _addNote() async {
    final l = AppLocalizations.of(context);
    final ctrl = TextEditingController();
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(24, 24, 24, MediaQuery.of(ctx).viewInsets.bottom + 24),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(l.tr('urgent_note_title'), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text(l.tr('urgent_note_hint'), style: TextStyle(color: AppColors.textSecondary, fontSize: 14, height: 1.4)),
          const SizedBox(height: 16),
          TextField(controller: ctrl, maxLines: 4, decoration: InputDecoration(hintText: l.tr('urgent_note_hint'))),
          const SizedBox(height: 16),
          SizedBox(height: 52, child: ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(l.tr('save_note')),
          )),
        ]),
      ),
    );
    if (saved != true || ctrl.text.trim().isEmpty) return;
    try {
      final api = ref.read(apiClientProvider);
      await api.dio.post('/api/v1/urgent/notes', data: {'note_text': ctrl.text.trim(), 'observed_symptoms': []});
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.tr('note_saved')), backgroundColor: AppColors.success),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.tr('error_generic')), backgroundColor: AppColors.error),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l.tr('urgent_help')),
        actions: [IconButton(icon: const Icon(Icons.refresh_rounded), onPressed: _load, tooltip: l.tr('retry'))],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addNote,
        backgroundColor: AppColors.primary,
        icon: const Icon(Icons.edit_note_rounded, color: Colors.white),
        label: Text(l.tr('add_note'), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : _error != null
              ? _ErrorView(message: _error!, onRetry: _load)
              : ResponsiveCenter(
                  child: ListView(
                    padding: Responsive.screenPadding(context).copyWith(top: 16, bottom: 96),
                    children: [
                      // ── App limitation statement ──
                      _SectionCard(
                        icon: Icons.info_outline_rounded,
                        iconColor: AppColors.primary,
                        title: l.tr('urgent_app_cannot'),
                        child: Text(
                          _info?['disclaimer'] ?? l.tr('urgent_disclaimer_fallback'),
                          style: const TextStyle(fontSize: 14, height: 1.5),
                        ),
                      ),
                      const SizedBox(height: 16),

                      // ── Warning signs (seek care) ──
                      _SectionCard(
                        icon: Icons.warning_amber_rounded,
                        iconColor: AppColors.error,
                        title: l.tr('urgent_warning_signs'),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            for (final sign in (_info?['warning_signs'] as List<dynamic>? ?? const []))
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Icon(Icons.circle, size: 6, color: AppColors.error),
                                    const SizedBox(width: 10),
                                    Expanded(child: Text(sign.toString(), style: const TextStyle(fontSize: 14, height: 1.45))),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),

                      // ── Emergency contacts ──
                      _SectionCard(
                        icon: Icons.call_rounded,
                        iconColor: AppColors.error,
                        title: l.tr('urgent_contacts'),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            for (final line in (_info?['contact_guidance'] as List<dynamic>? ?? const []))
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Icon(Icons.circle, size: 6, color: AppColors.primary),
                                    const SizedBox(width: 10),
                                    Expanded(child: Text(line.toString(), style: const TextStyle(fontSize: 14, height: 1.45))),
                                  ],
                                ),
                              ),
                            const SizedBox(height: 4),
                            // Color-independent affordance: icon + text, tap to copy.
                            _CopyableNumber(number: '112', label: l.tr('emergency_number')),
                            _CopyableNumber(number: '108', label: l.tr('ambulance_number')),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),

                      // ── Clinician conversation checklist ──
                      _SectionCard(
                        icon: Icons.medical_information_outlined,
                        iconColor: AppColors.secondary,
                        title: l.tr('urgent_clinician_checklist'),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            for (final item in (_info?['clinician_checklist'] as List<dynamic>? ?? const []))
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Icon(Icons.check_box_outline_blank_rounded, size: 16, color: AppColors.secondary),
                                    const SizedBox(width: 10),
                                    Expanded(child: Text(item.toString(), style: const TextStyle(fontSize: 14, height: 1.45))),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),

                      // ── Saved notes ──
                      if (_notes.isNotEmpty) ...[
                        Text(l.tr('your_notes'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 8),
                        for (final note in _notes)
                          Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(14),
                              boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 10)],
                            ),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(note['note_text'] ?? '', style: const TextStyle(fontSize: 14, height: 1.45)),
                              const SizedBox(height: 6),
                              Text(
                                (note['created_at'] ?? '').toString().split('T').first,
                                style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                              ),
                            ]),
                          ),
                      ],
                    ],
                  ),
                ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final Widget child;
  const _SectionCard({required this.icon, required this.iconColor, required this.title, required this.child});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: iconColor.withValues(alpha: 0.15)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 12)],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            width: 38, height: 38,
            decoration: BoxDecoration(color: iconColor.withValues(alpha: 0.1), shape: BoxShape.circle),
            child: Icon(icon, color: iconColor, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(child: Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700))),
        ]),
        const SizedBox(height: 14),
        child,
      ]),
    );
  }
}

class _CopyableNumber extends StatelessWidget {
  final String number;
  final String label;
  const _CopyableNumber({required this.number, required this.label});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(children: [
        Text('$label: ', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        Text(number, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: AppColors.error)),
        const SizedBox(width: 6),
        GestureDetector(
          onTap: () {
            Clipboard.setData(ClipboardData(text: number));
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('$number copied to clipboard'), duration: const Duration(seconds: 1)),
            );
          },
          child: const Icon(Icons.copy_rounded, size: 15, color: AppColors.textSecondary),
        ),
      ]),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final Future<void> Function() onRetry;
  const _ErrorView({required this.message, required this.onRetry});
  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Center(child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Icon(Icons.cloud_off_rounded, size: 48, color: AppColors.textSecondary),
        const SizedBox(height: 16),
        Text(message, textAlign: TextAlign.center, style: const TextStyle(fontSize: 15, height: 1.5)),
        const SizedBox(height: 20),
        ElevatedButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded),
          label: Text(l.tr('retry')),
        ),
      ]),
    ));
  }
}
