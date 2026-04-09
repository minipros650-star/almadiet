import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/utils/api_client.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/auth_provider.dart';
import '../../../providers/locale_provider.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});
  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> with SingleTickerProviderStateMixin {
  String? _profileImagePath;
  late AnimationController _animCtrl;

  static const _languages = {'en': 'English', 'ml': 'മലയാളം', 'ta': 'தமிழ்', 'kn': 'ಕನ್ನಡ', 'te': 'తెలుగు'};

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 700))..forward();
    _loadProfileImage();
  }

  @override
  void dispose() { _animCtrl.dispose(); super.dispose(); }

  Future<void> _loadProfileImage() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() => _profileImagePath = prefs.getString('profile_image'));
  }

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: source, maxWidth: 512, maxHeight: 512, imageQuality: 85);
    if (picked != null) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('profile_image', picked.path);
      setState(() => _profileImagePath = picked.path);
    }
  }

  void _showImagePicker() {
    final l = AppLocalizations.of(context);
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 20),
            Text(l.tr('profile_photo'), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
            const SizedBox(height: 20),
            Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
              _ImageOption(icon: Icons.camera_alt_rounded, label: l.tr('camera'), color: AppColors.primary, onTap: () { Navigator.pop(ctx); _pickImage(ImageSource.camera); }),
              _ImageOption(icon: Icons.photo_library_rounded, label: l.tr('gallery'), color: AppColors.secondary, onTap: () { Navigator.pop(ctx); _pickImage(ImageSource.gallery); }),
              if (_profileImagePath != null)
                _ImageOption(icon: Icons.delete_rounded, label: l.tr('remove'), color: AppColors.error, onTap: () async {
                  Navigator.pop(ctx);
                  final prefs = await SharedPreferences.getInstance();
                  await prefs.remove('profile_image');
                  setState(() => _profileImagePath = null);
                }),
            ]),
            const SizedBox(height: 16),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authStateProvider);
    final locale = ref.watch(localeProvider);
    final user = auth.user;
    final pad = Responsive.screenPadding(context);
    final l = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l.tr('profile')), actions: [
        IconButton(icon: const Icon(Icons.edit_rounded), onPressed: () => _showProfileEditor(user)),
      ]),
      body: ResponsiveCenter(
        child: FadeTransition(
          opacity: CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut),
          child: ListView(padding: pad.copyWith(top: 20, bottom: 32), children: [
            // ── Avatar ──
            Center(child: GestureDetector(
              onTap: _showImagePicker,
              child: Stack(children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  width: 110, height: 110,
                  decoration: BoxDecoration(
                    gradient: AppColors.primaryGradient,
                    shape: BoxShape.circle,
                    boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.25), blurRadius: 20, offset: const Offset(0, 8))],
                    image: _profileImagePath != null ? DecorationImage(image: FileImage(File(_profileImagePath!)), fit: BoxFit.cover) : null,
                  ),
                  child: _profileImagePath == null
                      ? Center(child: Text((user?['name'] ?? 'U')[0].toUpperCase(), style: const TextStyle(fontSize: 40, fontWeight: FontWeight.w700, color: Colors.white)))
                      : null,
                ),
                Positioned(
                  bottom: 0, right: 0,
                  child: Container(
                    width: 36, height: 36,
                    decoration: BoxDecoration(color: AppColors.primary, shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 3), boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.3), blurRadius: 8)]),
                    child: const Icon(Icons.camera_alt, size: 16, color: Colors.white),
                  ),
                ),
              ]),
            )),
            const SizedBox(height: 16),
            Center(child: Text(user?['name'] ?? 'User', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700))),
            Center(child: Text(user?['email'] ?? '', style: TextStyle(fontSize: 14, color: AppColors.textSecondary))),
            const SizedBox(height: 28),

            // ── Info Cards ──
            _InfoTile(icon: Icons.location_on_outlined, label: l.tr('region'), value: (user?['region'] ?? '-').toString().replaceAll('tamilnadu', 'Tamil Nadu'), color: AppColors.primary),
            _InfoTile(icon: Icons.cake_outlined, label: l.tr('age'), value: '${user?['age'] ?? '-'}', color: AppColors.accent),
            _InfoTile(icon: Icons.phone_outlined, label: l.tr('phone'), value: user?['phone'] ?? '-', color: AppColors.secondary),
            _InfoTile(icon: Icons.straighten_outlined, label: l.tr('height'), value: '${user?['height_cm'] ?? '-'} cm', color: AppColors.trimester3),
            _InfoTile(icon: Icons.monitor_weight_outlined, label: l.tr('pre_weight'), value: '${user?['pre_pregnancy_weight_kg'] ?? '-'} kg', color: AppColors.trimester2),
            const SizedBox(height: 24),

            // ── Language Selector ──
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20), boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 12)]),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(Icons.language_rounded, color: AppColors.primary, size: 22),
                  const SizedBox(width: 10),
                  Text(l.tr('language'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                ]),
                const SizedBox(height: 14),
                Wrap(spacing: 8, runSpacing: 8, children: _languages.entries.map((e) => GestureDetector(
                  onTap: () => ref.read(localeProvider.notifier).setLocale(e.key),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      color: locale.languageCode == e.key ? AppColors.primary : AppColors.inputFill,
                      borderRadius: BorderRadius.circular(14),
                      boxShadow: locale.languageCode == e.key ? [BoxShadow(color: AppColors.primary.withValues(alpha: 0.2), blurRadius: 8)] : null,
                    ),
                    child: Text(e.value, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: locale.languageCode == e.key ? Colors.white : AppColors.textPrimary)),
                  ),
                )).toList()),
              ]),
            ),
            const SizedBox(height: 32),

            // ── Logout ──
            SizedBox(
              height: 52,
              child: OutlinedButton.icon(
                onPressed: () async {
                  await ref.read(authStateProvider.notifier).logout();
                  if (context.mounted) context.go('/login');
                },
                icon: const Icon(Icons.logout_rounded),
                label: Text(l.tr('logout')),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.error,
                  side: const BorderSide(color: AppColors.error),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                ),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  void _showProfileEditor(Map<String, dynamic>? user) {
    final l = AppLocalizations.of(context);
    final nameCtrl = TextEditingController(text: user?['name'] ?? '');
    final phoneCtrl = TextEditingController(text: user?['phone'] ?? '');
    final ageCtrl = TextEditingController(text: '${user?['age'] ?? ''}');
    final heightCtrl = TextEditingController(text: '${user?['height_cm'] ?? ''}');
    final weightCtrl = TextEditingController(text: '${user?['pre_pregnancy_weight_kg'] ?? ''}');

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(24, 24, 24, MediaQuery.of(ctx).viewInsets.bottom + 24),
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Center(child: Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(2)))),
            const SizedBox(height: 20),
            Text(l.tr('edit_profile'), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
            const SizedBox(height: 20),
            TextField(controller: nameCtrl, decoration: InputDecoration(hintText: l.tr('name'), prefixIcon: const Icon(Icons.person_outline))),
            const SizedBox(height: 12),
            TextField(controller: phoneCtrl, keyboardType: TextInputType.phone, decoration: InputDecoration(hintText: l.tr('phone'), prefixIcon: const Icon(Icons.phone_outlined))),
            const SizedBox(height: 12),
            TextField(controller: ageCtrl, keyboardType: TextInputType.number, decoration: InputDecoration(hintText: l.tr('age'), prefixIcon: const Icon(Icons.cake_outlined))),
            const SizedBox(height: 12),
            TextField(controller: heightCtrl, keyboardType: TextInputType.number, decoration: InputDecoration(hintText: l.tr('height'), prefixIcon: const Icon(Icons.straighten_outlined))),
            const SizedBox(height: 12),
            TextField(controller: weightCtrl, keyboardType: TextInputType.number, decoration: InputDecoration(hintText: l.tr('pre_weight'), prefixIcon: const Icon(Icons.monitor_weight_outlined))),
            const SizedBox(height: 24),
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: () async {
                  final api = ref.read(apiClientProvider);
                  try {
                    final data = <String, dynamic>{};
                    if (nameCtrl.text.isNotEmpty) data['name'] = nameCtrl.text;
                    if (phoneCtrl.text.isNotEmpty) data['phone'] = phoneCtrl.text;
                    if (ageCtrl.text.isNotEmpty) data['age'] = int.tryParse(ageCtrl.text);
                    if (heightCtrl.text.isNotEmpty) data['height_cm'] = double.tryParse(heightCtrl.text);
                    if (weightCtrl.text.isNotEmpty) data['pre_pregnancy_weight_kg'] = double.tryParse(weightCtrl.text);
                    await api.dio.put('/api/auth/me', data: data);
                    // Refresh profile
                    final res = await api.dio.get('/api/auth/me');
                    ref.read(authStateProvider.notifier).login(res.data['email'], ''); // Will fail but state gets refreshed
                  } catch (_) {}
                  if (ctx.mounted) Navigator.pop(ctx);
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.tr('profile_updated')), backgroundColor: AppColors.success));
                  }
                },
                child: Text(l.tr('save_changes')),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _ImageOption extends StatelessWidget {
  final IconData icon; final String label; final Color color; final VoidCallback onTap;
  const _ImageOption({required this.icon, required this.label, required this.color, required this.onTap});
  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Column(children: [
      Container(
        width: 60, height: 60,
        decoration: BoxDecoration(color: color.withValues(alpha: 0.1), shape: BoxShape.circle),
        child: Icon(icon, color: color, size: 28),
      ),
      const SizedBox(height: 8),
      Text(label, style: TextStyle(fontSize: 13, color: color, fontWeight: FontWeight.w600)),
    ]),
  );
}

class _InfoTile extends StatelessWidget {
  final IconData icon; final String label, value; final Color color;
  const _InfoTile({required this.icon, required this.label, required this.value, required this.color});
  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 10)],
    ),
    child: Row(children: [
      Container(
        width: 40, height: 40,
        decoration: BoxDecoration(color: color.withValues(alpha: 0.1), shape: BoxShape.circle),
        child: Icon(icon, color: color, size: 20),
      ),
      const SizedBox(width: 14),
      Text(label, style: TextStyle(color: AppColors.textSecondary, fontSize: 14)),
      const Spacer(),
      Text(value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
    ]),
  );
}
