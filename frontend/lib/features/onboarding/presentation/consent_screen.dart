import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/auth_provider.dart';

/// Current consent version — bump when docs/PRIVACY_AND_DATA.md changes
/// materially. Backend stores (version, timestamp) per user.
const kConsentVersion = '2026-09-v1';

class ConsentScreen extends ConsumerStatefulWidget {
  const ConsentScreen({super.key});
  @override
  ConsumerState<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends ConsumerState<ConsentScreen> {
  bool _saving = false;

  Future<void> _agree() async {
    final l = AppLocalizations.of(context);
    setState(() => _saving = true);
    final ok = await ref.read(authStateProvider.notifier).acceptConsent(kConsentVersion);
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      context.go('/home');
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(l.tr('error_generic')),
        backgroundColor: AppColors.error,
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l.tr('consent_title'))),
      body: ResponsiveSafeCenter(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: AppColors.primary.withValues(alpha: 0.15)),
                ),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(Icons.privacy_tip_outlined, size: 26, color: AppColors.primary),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text(l.tr('consent_title'), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                  ),
                ]),
              ),
              const SizedBox(height: 20),
              Expanded(
                child: SingleChildScrollView(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(l.tr('consent_body'), style: const TextStyle(fontSize: 15, height: 1.6)),
                    const SizedBox(height: 16),
                    Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(Icons.download_rounded, size: 18, color: AppColors.textSecondary),
                      const SizedBox(width: 10),
                      Expanded(child: Text(l.tr('consent_privacy'), style: TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.5))),
                    ]),
                  ]),
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                height: 56,
                child: ElevatedButton(
                  onPressed: _saving ? null : _agree,
                  style: ElevatedButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
                  child: _saving
                      ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : Text(l.tr('consent_agree'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ResponsiveSafeCenter extends StatelessWidget {
  final Widget child;
  const ResponsiveSafeCenter({super.key, required this.child});
  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: child,
        ),
      ),
    );
  }
}
