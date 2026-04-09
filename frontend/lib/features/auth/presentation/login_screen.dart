import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/localization/app_localizations.dart';
import '../../../providers/auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});
  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> with TickerProviderStateMixin {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _obscure = true;
  late AnimationController _fadeCtrl;
  late AnimationController _floatCtrl;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _fadeCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..forward();
    _floatCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat(reverse: true);
    _fadeAnim = CurvedAnimation(parent: _fadeCtrl, curve: Curves.easeOutCubic);
    _slideAnim = Tween<Offset>(begin: const Offset(0, 0.08), end: Offset.zero).animate(_fadeAnim);
  }

  @override
  void dispose() { _fadeCtrl.dispose(); _floatCtrl.dispose(); _emailCtrl.dispose(); _passCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authStateProvider);
    final l = AppLocalizations.of(context);

    return Scaffold(
      body: Stack(
        children: [
          // Floating background decorations
          ..._buildBgDecorations(context),

          SafeArea(
            child: FadeTransition(
              opacity: _fadeAnim,
              child: SlideTransition(
                position: _slideAnim,
                child: ResponsiveCenter(
                  child: SingleChildScrollView(
                    padding: Responsive.screenPadding(context).copyWith(top: 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SizedBox(height: MediaQuery.of(context).size.height * 0.08),
                        // Animated logo
                        Center(child: _AnimatedLogo(controller: _floatCtrl)),
                        const SizedBox(height: 28),
                        Text(l.tr('welcome_back'), style: TextStyle(fontSize: 30 * Responsive.fontScale(context), fontWeight: FontWeight.w800, color: AppColors.textPrimary), textAlign: TextAlign.center),
                        const SizedBox(height: 6),
                        Text(l.tr('sign_in_continue'), style: TextStyle(fontSize: 15, color: AppColors.textSecondary), textAlign: TextAlign.center),
                        const SizedBox(height: 44),

                        // Email
                        _AnimatedField(
                          delay: 200,
                          child: TextField(
                            controller: _emailCtrl,
                            keyboardType: TextInputType.emailAddress,
                            decoration: InputDecoration(
                              hintText: l.tr('email'),
                              prefixIcon: Icon(Icons.email_outlined, color: AppColors.primary.withValues(alpha: 0.6)),
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Password
                        _AnimatedField(
                          delay: 350,
                          child: TextField(
                            controller: _passCtrl,
                            obscureText: _obscure,
                            decoration: InputDecoration(
                              hintText: l.tr('password'),
                              prefixIcon: Icon(Icons.lock_outline, color: AppColors.primary.withValues(alpha: 0.6)),
                              suffixIcon: IconButton(
                                icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility, color: AppColors.textHint),
                                onPressed: () => setState(() => _obscure = !_obscure),
                              ),
                            ),
                          ),
                        ),

                        // Error
                        if (authState.error != null) ...[
                          const SizedBox(height: 16),
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(color: AppColors.error.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(12)),
                            child: Row(children: [
                              const Icon(Icons.error_outline, color: AppColors.error, size: 18),
                              const SizedBox(width: 8),
                              Expanded(child: Text(authState.error!, style: const TextStyle(color: AppColors.error, fontSize: 13))),
                            ]),
                          ),
                        ],

                        const SizedBox(height: 28),

                        // Login button
                        _AnimatedField(
                          delay: 500,
                          child: SizedBox(
                            height: 58,
                            child: ElevatedButton(
                              onPressed: authState.isLoading ? null : () async {
                                final ok = await ref.read(authStateProvider.notifier).login(_emailCtrl.text.trim(), _passCtrl.text);
                                if (ok && context.mounted) context.go('/home');
                              },
                              style: ElevatedButton.styleFrom(
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                                elevation: 4,
                                shadowColor: AppColors.primary.withValues(alpha: 0.3),
                              ),
                              child: authState.isLoading
                                  ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5))
                                  : Text(l.tr('sign_in'), style: const TextStyle(fontSize: 17)),
                            ),
                          ),
                        ),
                        const SizedBox(height: 28),

                        // Register link
                        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                          Text(l.tr('no_account'), style: TextStyle(color: AppColors.textSecondary)),
                          GestureDetector(
                            onTap: () => context.go('/register'),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: AppColors.primary.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(l.tr('register'), style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700)),
                            ),
                          ),
                        ]),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildBgDecorations(BuildContext context) {
    final h = MediaQuery.of(context).size.height;
    return [
      AnimatedBuilder(
        animation: _floatCtrl,
        builder: (_, _) => Positioned(
          top: -30 + _floatCtrl.value * 20,
          right: -40,
          child: Container(
            width: 200, height: 200,
            decoration: BoxDecoration(shape: BoxShape.circle, color: AppColors.primaryLight.withValues(alpha: 0.06)),
          ),
        ),
      ),
      AnimatedBuilder(
        animation: _floatCtrl,
        builder: (_, _) => Positioned(
          bottom: h * 0.2 - 20 + _floatCtrl.value * 15,
          left: -60,
          child: Container(
            width: 160, height: 160,
            decoration: BoxDecoration(shape: BoxShape.circle, color: AppColors.secondaryLight.withValues(alpha: 0.06)),
          ),
        ),
      ),
    ];
  }
}

class _AnimatedLogo extends StatelessWidget {
  final AnimationController controller;
  const _AnimatedLogo({required this.controller});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (_, _) => Transform.translate(
        offset: Offset(0, sin(controller.value * pi) * 6),
        child: Container(
          width: 90, height: 90,
          decoration: BoxDecoration(
            gradient: AppColors.primaryGradient,
            shape: BoxShape.circle,
            boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.25), blurRadius: 20 + controller.value * 8, offset: const Offset(0, 8))],
          ),
          child: const Center(child: Text('🌸', style: TextStyle(fontSize: 40))),
        ),
      ),
    );
  }
}

class _AnimatedField extends StatefulWidget {
  final Widget child;
  final int delay;
  const _AnimatedField({required this.child, this.delay = 0});
  @override
  State<_AnimatedField> createState() => _AnimatedFieldState();
}

class _AnimatedFieldState extends State<_AnimatedField> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 600));
    Future.delayed(Duration(milliseconds: widget.delay), () { if (mounted) _ctrl.forward(); });
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, _) {
        final t = Curves.easeOutCubic.transform(_ctrl.value);
        return Opacity(
          opacity: t,
          child: Transform.translate(offset: Offset(0, 20 * (1 - t)), child: widget.child),
        );
      },
    );
  }
}
