import 'dart:math';
import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// Pregnancy-themed loading animation with floating hearts and gentle pulse
class PregnancyLoader extends StatefulWidget {
  final String? message;
  const PregnancyLoader({super.key, this.message});

  @override
  State<PregnancyLoader> createState() => _PregnancyLoaderState();
}

class _PregnancyLoaderState extends State<PregnancyLoader> with TickerProviderStateMixin {
  late AnimationController _pulseCtrl;
  late AnimationController _rotateCtrl;
  late AnimationController _heartsCtrl;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);
    _rotateCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
    _heartsCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat();
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _rotateCtrl.dispose();
    _heartsCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 120, height: 120,
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Floating hearts
                ..._buildFloatingHearts(),
                // Pulsing circle
                AnimatedBuilder(
                  animation: _pulseCtrl,
                  builder: (_, _) => Transform.scale(
                    scale: 0.85 + (_pulseCtrl.value * 0.15),
                    child: Container(
                      width: 72, height: 72,
                      decoration: BoxDecoration(
                        gradient: AppColors.primaryGradient,
                        shape: BoxShape.circle,
                        boxShadow: [BoxShadow(
                          color: AppColors.primary.withValues(alpha: 0.2 + (_pulseCtrl.value * 0.15)),
                          blurRadius: 20 + (_pulseCtrl.value * 10),
                          spreadRadius: 2,
                        )],
                      ),
                      child: const Icon(Icons.favorite_rounded, color: Colors.white, size: 32),
                    ),
                  ),
                ),
                // Orbiting dots
                AnimatedBuilder(
                  animation: _rotateCtrl,
                  builder: (_, _) => Transform.rotate(
                    angle: _rotateCtrl.value * 2 * pi,
                    child: const SizedBox(
                      width: 100, height: 100,
                      child: Align(
                        alignment: Alignment.topCenter,
                        child: _OrbitDot(color: AppColors.secondary, size: 8),
                      ),
                    ),
                  ),
                ),
                AnimatedBuilder(
                  animation: _rotateCtrl,
                  builder: (_, _) => Transform.rotate(
                    angle: (_rotateCtrl.value * 2 * pi) + (pi * 0.67),
                    child: const SizedBox(
                      width: 100, height: 100,
                      child: Align(
                        alignment: Alignment.topCenter,
                        child: _OrbitDot(color: AppColors.accent, size: 6),
                      ),
                    ),
                  ),
                ),
                AnimatedBuilder(
                  animation: _rotateCtrl,
                  builder: (_, _) => Transform.rotate(
                    angle: (_rotateCtrl.value * 2 * pi) + (pi * 1.33),
                    child: const SizedBox(
                      width: 100, height: 100,
                      child: Align(
                        alignment: Alignment.topCenter,
                        child: _OrbitDot(color: AppColors.trimester3, size: 7),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (widget.message != null) ...[
            const SizedBox(height: 24),
            AnimatedBuilder(
              animation: _pulseCtrl,
              builder: (_, _) => Opacity(
                opacity: 0.5 + (_pulseCtrl.value * 0.5),
                child: Text(
                  widget.message!,
                  style: TextStyle(fontSize: 15, color: AppColors.textSecondary, fontWeight: FontWeight.w500),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  List<Widget> _buildFloatingHearts() {
    const heartIcons = ['💕', '🌸', '✨', '🤍', '💗'];
    return List.generate(5, (i) {
      return AnimatedBuilder(
        animation: _heartsCtrl,
        builder: (_, _) {
          final progress = (_heartsCtrl.value + (i * 0.2)) % 1.0;
          final angle = progress * 2 * pi;
          final radius = 45.0 + (sin(progress * pi) * 10);
          return Positioned(
            left: 60 + cos(angle + (i * 0.5)) * radius - 8,
            top: 60 + sin(angle + (i * 0.5)) * radius - 8,
            child: Opacity(
              opacity: (sin(progress * pi) * 0.6).clamp(0.0, 1.0),
              child: Text(heartIcons[i], style: const TextStyle(fontSize: 14)),
            ),
          );
        },
      );
    });
  }
}

class _OrbitDot extends StatelessWidget {
  final Color color;
  final double size;
  const _OrbitDot({required this.color, required this.size});
  @override
  Widget build(BuildContext context) {
    return Container(
      width: size, height: size,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle, boxShadow: [BoxShadow(color: color.withValues(alpha: 0.4), blurRadius: 6)]),
    );
  }
}

/// Shimmer loading skeleton
class ShimmerBox extends StatefulWidget {
  final double width, height;
  final double borderRadius;
  const ShimmerBox({super.key, required this.width, required this.height, this.borderRadius = 12});

  @override
  State<ShimmerBox> createState() => _ShimmerBoxState();
}

class _ShimmerBoxState extends State<ShimmerBox> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))..repeat();
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, _) => Container(
        width: widget.width, height: widget.height,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(widget.borderRadius),
          gradient: LinearGradient(
            begin: Alignment(-1 + (_ctrl.value * 3), 0),
            end: Alignment(_ctrl.value * 3, 0),
            colors: [
              const Color(0xFFF0E8F0),
              const Color(0xFFFAF2FA),
              const Color(0xFFF0E8F0),
            ],
          ),
        ),
      ),
    );
  }
}

/// Loading overlay with pregnancy theme
class LoadingOverlay extends StatelessWidget {
  final String? message;
  const LoadingOverlay({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.white.withValues(alpha: 0.85),
      child: PregnancyLoader(message: message),
    );
  }
}

/// Staggered list animation wrapper
class StaggeredItem extends StatelessWidget {
  final Widget child;
  final int index;
  final Duration baseDelay;

  const StaggeredItem({super.key, required this.child, required this.index, this.baseDelay = const Duration(milliseconds: 80)});

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeOutCubic,
      builder: (context, value, child) => Opacity(
        opacity: value,
        child: Transform.translate(
          offset: Offset(0, 30 * (1 - value)),
          child: child,
        ),
      ),
      child: child,
    );
  }
}
