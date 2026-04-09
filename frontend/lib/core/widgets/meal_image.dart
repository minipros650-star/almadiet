import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// A reusable widget that displays a meal image from a network URL
/// with graceful loading states, error handling, and rounded corners.
class MealImage extends StatelessWidget {
  final String? imageUrl;
  final double width;
  final double height;
  final double borderRadius;
  final BoxFit fit;
  final Color? placeholderColor;

  const MealImage({
    super.key,
    required this.imageUrl,
    this.width = 50,
    this.height = 50,
    this.borderRadius = 15,
    this.fit = BoxFit.cover,
    this.placeholderColor,
  });

  @override
  Widget build(BuildContext context) {
    final bgColor = placeholderColor ?? AppColors.primaryLight.withValues(alpha: 0.12);

    if (imageUrl == null || imageUrl!.isEmpty) {
      return _placeholder(bgColor);
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: SizedBox(
        width: width,
        height: height,
        child: Image.network(
          imageUrl!,
          width: width,
          height: height,
          fit: fit,
          loadingBuilder: (context, child, loadingProgress) {
            if (loadingProgress == null) return child;
            return Container(
              width: width,
              height: height,
              decoration: BoxDecoration(color: bgColor),
              child: Center(
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: const AlwaysStoppedAnimation(AppColors.primary),
                    value: loadingProgress.expectedTotalBytes != null
                        ? loadingProgress.cumulativeBytesLoaded / loadingProgress.expectedTotalBytes!
                        : null,
                  ),
                ),
              ),
            );
          },
          errorBuilder: (context, error, stackTrace) => _placeholder(bgColor),
        ),
      ),
    );
  }

  Widget _placeholder(Color bgColor) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(borderRadius),
      ),
      child: Icon(
        Icons.restaurant,
        color: AppColors.primary,
        size: width * 0.48,
      ),
    );
  }
}

/// Larger meal image for detail/hero views with gradient overlay.
class MealHeroImage extends StatelessWidget {
  final String? imageUrl;
  final double height;

  const MealHeroImage({
    super.key,
    required this.imageUrl,
    this.height = 220,
  });

  @override
  Widget build(BuildContext context) {
    if (imageUrl == null || imageUrl!.isEmpty) {
      return Container(
        height: height,
        decoration: const BoxDecoration(gradient: AppColors.warmGradient),
        child: const Center(
          child: Text('🍽️', style: TextStyle(fontSize: 64)),
        ),
      );
    }

    return SizedBox(
      height: height,
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image.network(
            imageUrl!,
            fit: BoxFit.cover,
            loadingBuilder: (context, child, loadingProgress) {
              if (loadingProgress == null) return child;
              return Container(
                decoration: const BoxDecoration(gradient: AppColors.warmGradient),
                child: Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Text('🍽️', style: TextStyle(fontSize: 48)),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: 32,
                      height: 32,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        valueColor: const AlwaysStoppedAnimation(Colors.white70),
                        value: loadingProgress.expectedTotalBytes != null
                            ? loadingProgress.cumulativeBytesLoaded / loadingProgress.expectedTotalBytes!
                            : null,
                      ),
                    ),
                  ]),
                ),
              );
            },
            errorBuilder: (context, error, stackTrace) => Container(
              decoration: const BoxDecoration(gradient: AppColors.warmGradient),
              child: const Center(
                child: Text('🍽️', style: TextStyle(fontSize: 64)),
              ),
            ),
          ),
          // Gradient overlay for text readability
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            height: height * 0.5,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.55),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
