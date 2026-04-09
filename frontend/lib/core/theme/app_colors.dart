import 'package:flutter/material.dart';

class AppColors {
  AppColors._();

  // Primary palette — warm, calming pregnancy-focused
  static const Color primary = Color(0xFFE91E8C);      // Rose Pink
  static const Color primaryLight = Color(0xFFFF6EB4);
  static const Color primaryDark = Color(0xFFB0156A);

  // Secondary
  static const Color secondary = Color(0xFF7C4DFF);     // Soft Purple
  static const Color secondaryLight = Color(0xFFB388FF);
  static const Color accent = Color(0xFFFF7043);        // Warm Coral

  // Background & Surface
  static const Color background = Color(0xFFFFF5F9);    // Blush White
  static const Color surface = Color(0xFFFFFFFF);
  static const Color inputFill = Color(0xFFF5F0F5);

  // Text
  static const Color textPrimary = Color(0xFF2D1B33);
  static const Color textSecondary = Color(0xFF7A6B80);
  static const Color textHint = Color(0xFFB0A3B5);

  // Status
  static const Color success = Color(0xFF4CAF50);
  static const Color warning = Color(0xFFFFA726);
  static const Color error = Color(0xFFE53935);
  static const Color info = Color(0xFF29B6F6);

  // Gradients
  static const LinearGradient primaryGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [primary, secondary],
  );

  static const LinearGradient warmGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFFFF6EB4), Color(0xFFFF7043)],
  );

  static const LinearGradient calmGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF7C4DFF), Color(0xFF29B6F6)],
  );

  // Trimester colors
  static const Color trimester1 = Color(0xFFFF8A80);   // Soft Red
  static const Color trimester2 = Color(0xFFFFAB40);   // Warm Orange
  static const Color trimester3 = Color(0xFF69F0AE);   // Fresh Green
}
