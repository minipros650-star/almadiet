import 'dart:math';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/responsive.dart';
import '../../../core/localization/app_localizations.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});
  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> with TickerProviderStateMixin {
  final _controller = PageController();
  int _currentPage = 0;
  late AnimationController _bgCtrl;
  late AnimationController _floatingCtrl;

  @override
  void initState() {
    super.initState();
    _bgCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 8))..repeat();
    _floatingCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat(reverse: true);
  }

  @override
  void dispose() { _bgCtrl.dispose(); _floatingCtrl.dispose(); _controller.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Scaffold(
      body: Stack(
        children: [
          // Animated gradient background
          AnimatedBuilder(
            animation: _bgCtrl,
            builder: (_, _) => Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment(cos(_bgCtrl.value * 2 * pi), sin(_bgCtrl.value * 2 * pi)),
                  end: Alignment(-cos(_bgCtrl.value * 2 * pi), -sin(_bgCtrl.value * 2 * pi)),
                  colors: [
                    AppColors.background,
                    Color.lerp(AppColors.primaryLight.withValues(alpha: 0.1), AppColors.secondaryLight.withValues(alpha: 0.1), _bgCtrl.value)!,
                    AppColors.background,
                  ],
                ),
              ),
            ),
          ),
          // Floating decorations
          ..._buildFloatingElements(),

          // Pages
          ResponsiveCenter(
            child: PageView(
              controller: _controller,
              onPageChanged: (i) => setState(() => _currentPage = i),
              children: [
                _OnboardPage(
                  icon: Icons.restaurant_rounded,
                  emoji: '🍽️',
                  title: l.tr('onboard_1_title'),
                  description: l.tr('onboard_1_desc'),
                  gradient: AppColors.primaryGradient,
                  decorEmojis: const ['🥗', '🍛', '🥘', '🫕'],
                ),
                _OnboardPage(
                  icon: Icons.psychology_rounded,
                  emoji: '🤖',
                  title: l.tr('onboard_2_title'),
                  description: l.tr('onboard_2_desc'),
                  gradient: AppColors.calmGradient,
                  decorEmojis: const ['📊', '🧠', '💡', '✨'],
                ),
                _OnboardPage(
                  icon: Icons.language_rounded,
                  emoji: '🌍',
                  title: l.tr('onboard_3_title'),
                  description: l.tr('onboard_3_desc'),
                  gradient: AppColors.warmGradient,
                  decorEmojis: const ['🌸', '🪷', '🌺', '💐'],
                ),
              ],
            ),
          ),

          // Skip button
          Positioned(
            top: MediaQuery.of(context).padding.top + 12,
            right: 20,
            child: AnimatedOpacity(
              opacity: _currentPage < 2 ? 1.0 : 0.0,
              duration: const Duration(milliseconds: 300),
              child: TextButton(
                onPressed: () => context.go('/login'),
                style: TextButton.styleFrom(
                  backgroundColor: AppColors.primary.withValues(alpha: 0.08),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                ),
                child: Text(l.tr('skip'), style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600)),
              ),
            ),
          ),

          // Bottom controls
          Positioned(
            bottom: MediaQuery.of(context).padding.bottom + 40,
            left: 0, right: 0,
            child: Column(children: [
              // Animated page indicators
              Row(mainAxisAlignment: MainAxisAlignment.center, children: List.generate(3, (i) => AnimatedContainer(
                duration: const Duration(milliseconds: 350),
                curve: Curves.easeOutCubic,
                margin: const EdgeInsets.symmetric(horizontal: 5),
                width: _currentPage == i ? 36 : 10,
                height: 10,
                decoration: BoxDecoration(
                  gradient: _currentPage == i ? AppColors.primaryGradient : null,
                  color: _currentPage == i ? null : AppColors.primaryLight.withValues(alpha: 0.25),
                  borderRadius: BorderRadius.circular(5),
                  boxShadow: _currentPage == i ? [BoxShadow(color: AppColors.primary.withValues(alpha: 0.3), blurRadius: 8)] : null,
                ),
              ))),
              const SizedBox(height: 36),
              // Button
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 40),
                child: SizedBox(
                  width: double.infinity, height: 58,
                  child: ElevatedButton(
                    onPressed: () {
                      if (_currentPage < 2) {
                        _controller.nextPage(duration: const Duration(milliseconds: 500), curve: Curves.easeOutCubic);
                      } else {
                        context.go('/login');
                      }
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                      elevation: 4,
                      shadowColor: AppColors.primary.withValues(alpha: 0.3),
                    ),
                    child: Text(
                      _currentPage < 2 ? '${l.tr('next')}  →' : '✨ ${l.tr('get_started')}',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white),
                    ),
                  ),
                ),
              ),
            ]),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildFloatingElements() {
    const emojis = ['🌸', '💕', '✨', '🤍', '🌺', '💗'];
    return List.generate(6, (i) {
      final screenW = MediaQuery.of(context).size.width;
      final screenH = MediaQuery.of(context).size.height;
      return AnimatedBuilder(
        animation: _floatingCtrl,
        builder: (_, _) {
          final x = (i * screenW / 5) + sin((_floatingCtrl.value + i * 0.3) * pi) * 20;
          final y = (i * screenH / 7) + 50 + cos((_floatingCtrl.value + i * 0.5) * pi) * 30;
          return Positioned(
            left: x.clamp(0, screenW - 30),
            top: y.clamp(0, screenH - 30),
            child: Opacity(
              opacity: 0.15,
              child: Text(emojis[i], style: const TextStyle(fontSize: 24)),
            ),
          );
        },
      );
    });
  }
}

class _OnboardPage extends StatefulWidget {
  final IconData icon;
  final String emoji;
  final String title;
  final String description;
  final LinearGradient gradient;
  final List<String> decorEmojis;

  const _OnboardPage({
    required this.icon, required this.emoji, required this.title,
    required this.description, required this.gradient, required this.decorEmojis,
  });

  @override
  State<_OnboardPage> createState() => _OnboardPageState();
}

class _OnboardPageState extends State<_OnboardPage> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat(reverse: true);
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 36),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        // Animated icon with orbiting emojis
        SizedBox(
          width: 200, height: 200,
          child: Stack(alignment: Alignment.center, children: [
            // Orbiting emojis
            ...List.generate(widget.decorEmojis.length, (i) => AnimatedBuilder(
              animation: _ctrl,
              builder: (_, _) {
                final angle = (i / widget.decorEmojis.length) * 2 * pi + (_ctrl.value * 2 * pi);
                final r = 80.0;
                return Positioned(
                  left: 100 + cos(angle) * r - 12,
                  top: 100 + sin(angle) * r - 12,
                  child: Opacity(
                    opacity: 0.6 + sin((_ctrl.value + i * 0.25) * pi) * 0.4,
                    child: Text(widget.decorEmojis[i], style: const TextStyle(fontSize: 22)),
                  ),
                );
              },
            )),
            // Main icon
            AnimatedBuilder(
              animation: _ctrl,
              builder: (_, _) => Transform.scale(
                scale: 0.9 + (_ctrl.value * 0.1),
                child: Container(
                  width: 100, height: 100,
                  decoration: BoxDecoration(
                    gradient: widget.gradient,
                    shape: BoxShape.circle,
                    boxShadow: [BoxShadow(color: widget.gradient.colors.first.withValues(alpha: 0.3), blurRadius: 30 + (_ctrl.value * 10), spreadRadius: 2)],
                  ),
                  child: Center(child: Text(widget.emoji, style: const TextStyle(fontSize: 44))),
                ),
              ),
            ),
          ]),
        ),
        const SizedBox(height: 48),
        Text(widget.title, style: TextStyle(fontSize: 28 * Responsive.fontScale(context), fontWeight: FontWeight.w800, color: AppColors.textPrimary), textAlign: TextAlign.center),
        const SizedBox(height: 16),
        Text(widget.description, style: TextStyle(fontSize: 15, color: AppColors.textSecondary, height: 1.6), textAlign: TextAlign.center),
      ]),
    );
  }
}
