import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/auth_provider.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});
  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> with TickerProviderStateMixin {
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _ageCtrl = TextEditingController();
  String _region = 'kerala';
  String _language = 'en';
  bool _obscure = true;
  late AnimationController _animCtrl;

  static const _regions = {'kerala': '🌴 Kerala', 'tamilnadu': '🛕 Tamil Nadu', 'karnataka': '🏛️ Karnataka', 'andhra': '🌶️ Andhra Pradesh'};
  static const _languages = {'en': '🇬🇧 English', 'ml': '🇮🇳 Malayalam', 'ta': '🇮🇳 Tamil', 'kn': '🇮🇳 Kannada', 'te': '🇮🇳 Telugu'};

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..forward();
  }

  @override
  void dispose() { _animCtrl.dispose(); _nameCtrl.dispose(); _emailCtrl.dispose(); _passCtrl.dispose(); _ageCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authStateProvider);
    final l = AppLocalizations.of(context);

    return Scaffold(
      body: SafeArea(
        child: FadeTransition(
          opacity: CurvedAnimation(parent: _animCtrl, curve: Curves.easeOutCubic),
          child: ResponsiveCenter(
            child: SingleChildScrollView(
              padding: Responsive.screenPadding(context).copyWith(top: 32, bottom: 32),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                // Header
                Center(child: Container(
                  width: 70, height: 70,
                  decoration: BoxDecoration(gradient: AppColors.calmGradient, shape: BoxShape.circle, boxShadow: [BoxShadow(color: AppColors.secondary.withValues(alpha: 0.2), blurRadius: 16)]),
                  child: const Center(child: Text('👶', style: TextStyle(fontSize: 32))),
                )),
                const SizedBox(height: 20),
                Text(l.tr('create_account'), style: TextStyle(fontSize: 28 * Responsive.fontScale(context), fontWeight: FontWeight.w800, color: AppColors.textPrimary), textAlign: TextAlign.center),
                const SizedBox(height: 6),
                Text(l.tr('start_journey'), style: TextStyle(fontSize: 14, color: AppColors.textSecondary), textAlign: TextAlign.center),
                const SizedBox(height: 32),

                // Fields
                _buildField(Icons.person_outline, l.tr('name'), _nameCtrl),
                const SizedBox(height: 14),
                _buildField(Icons.email_outlined, l.tr('email'), _emailCtrl, type: TextInputType.emailAddress),
                const SizedBox(height: 14),
                TextField(
                  controller: _passCtrl, obscureText: _obscure,
                  decoration: InputDecoration(
                    hintText: l.tr('password'),
                    prefixIcon: Icon(Icons.lock_outline, color: AppColors.primary.withValues(alpha: 0.6)),
                    suffixIcon: IconButton(icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility, color: AppColors.textHint), onPressed: () => setState(() => _obscure = !_obscure)),
                  ),
                ),
                const SizedBox(height: 14),
                _buildField(Icons.cake_outlined, l.tr('age'), _ageCtrl, type: TextInputType.number),
                const SizedBox(height: 14),

                // Region dropdown
                _buildDropdown(l.tr('region'), _region, _regions, Icons.location_on_outlined, (v) => setState(() => _region = v!)),
                const SizedBox(height: 14),
                _buildDropdown(l.tr('language'), _language, _languages, Icons.language, (v) => setState(() => _language = v!)),
                const SizedBox(height: 20),

                // Error
                if (authState.error != null)
                  Container(
                    margin: const EdgeInsets.only(bottom: 16),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(color: AppColors.error.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(12)),
                    child: Text(authState.error!, style: const TextStyle(color: AppColors.error, fontSize: 13), textAlign: TextAlign.center),
                  ),

                // Submit button
                SizedBox(
                  height: 58,
                  child: ElevatedButton(
                    onPressed: authState.isLoading ? null : () async {
                      final ok = await ref.read(authStateProvider.notifier).register(
                        email: _emailCtrl.text.trim(), password: _passCtrl.text, name: _nameCtrl.text.trim(),
                        region: _region, language: _language, age: int.tryParse(_ageCtrl.text),
                      );
                      if (ok && context.mounted) context.go('/home');
                    },
                    style: ElevatedButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)), elevation: 4, shadowColor: AppColors.primary.withValues(alpha: 0.3)),
                    child: authState.isLoading
                        ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5))
                        : Text('${l.tr('create_account')} ✨', style: const TextStyle(fontSize: 17)),
                  ),
                ),
                const SizedBox(height: 24),

                // Login link
                Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Text(l.tr('has_account'), style: TextStyle(color: AppColors.textSecondary)),
                  GestureDetector(
                    onTap: () => context.go('/login'),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(color: AppColors.primary.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(8)),
                      child: Text(l.tr('sign_in'), style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700)),
                    ),
                  ),
                ]),
              ]),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildField(IconData icon, String hint, TextEditingController ctrl, {TextInputType type = TextInputType.text}) {
    return TextField(
      controller: ctrl, keyboardType: type,
      decoration: InputDecoration(hintText: hint, prefixIcon: Icon(icon, color: AppColors.primary.withValues(alpha: 0.6))),
    );
  }

  Widget _buildDropdown(String label, String value, Map<String, String> items, IconData icon, Function(String?) onChanged) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(color: AppColors.inputFill, borderRadius: BorderRadius.circular(14)),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: value, isExpanded: true,
          icon: const Icon(Icons.arrow_drop_down, color: AppColors.textSecondary),
          items: items.entries.map((e) => DropdownMenuItem(value: e.key, child: Row(children: [
            Icon(icon, size: 20, color: AppColors.primary.withValues(alpha: 0.6)),
            const SizedBox(width: 12),
            Text(e.value),
          ]))).toList(),
          onChanged: onChanged,
        ),
      ),
    );
  }
}
