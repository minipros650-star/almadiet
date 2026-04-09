import 'package:flutter/material.dart';

/// Responsive utility for adaptive layouts across devices.
class Responsive {
  static double width(BuildContext context) => MediaQuery.sizeOf(context).width;
  static double height(BuildContext context) => MediaQuery.sizeOf(context).height;

  static bool isMobile(BuildContext context) => width(context) < 600;
  static bool isTablet(BuildContext context) => width(context) >= 600 && width(context) < 1024;
  static bool isDesktop(BuildContext context) => width(context) >= 1024;

  /// Adaptive padding based on screen width
  static EdgeInsets screenPadding(BuildContext context) {
    final w = width(context);
    if (w < 400) return const EdgeInsets.symmetric(horizontal: 16);
    if (w < 600) return const EdgeInsets.symmetric(horizontal: 24);
    if (w < 1024) return const EdgeInsets.symmetric(horizontal: 40);
    return EdgeInsets.symmetric(horizontal: w * 0.15);
  }

  /// Max content width (centers on large screens)
  static double maxContentWidth(BuildContext context) {
    if (isDesktop(context)) return 600;
    if (isTablet(context)) return 500;
    return width(context);
  }

  /// Adaptive font scale
  static double fontScale(BuildContext context) {
    final w = width(context);
    if (w < 360) return 0.85;
    if (w < 400) return 0.92;
    return 1.0;
  }

  /// Adaptive grid columns
  static int gridColumns(BuildContext context) {
    if (isDesktop(context)) return 4;
    if (isTablet(context)) return 3;
    return 2;
  }
}

/// Centered content wrapper for large screens
class ResponsiveCenter extends StatelessWidget {
  final Widget child;
  final double maxWidth;
  const ResponsiveCenter({super.key, required this.child, this.maxWidth = 600});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: child,
      ),
    );
  }
}
