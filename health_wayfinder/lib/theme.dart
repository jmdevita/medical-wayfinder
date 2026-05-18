import 'package:flutter/material.dart';

class AppColors {
  static const teal = Color(0xFF1D9E75);
  static const tealLight = Color(0xFFE1F5EE);
  static const tealDark = Color(0xFF167A5B);
  static const amber = Color(0xFFEF9F27);
  static const amberLight = Color(0xFFFFF3DC);

  // Warm paper background (light mode only) — matches the mockup's cream feel.
  static const paper = Color(0xFFF5EEE0);
  static const paperSurface = Color(0xFFFBF7EE);

  static const gray50 = Color(0xFFF9FAFB);
  static const gray100 = Color(0xFFF3F4F6);
  static const gray200 = Color(0xFFE5E7EB);
  static const gray300 = Color(0xFFD1D5DB);
  static const gray400 = Color(0xFF9CA3AF);
  static const gray500 = Color(0xFF6B7280);
  static const gray600 = Color(0xFF4B5563);
  static const gray700 = Color(0xFF374151);
  static const gray800 = Color(0xFF1F2937);
  static const gray900 = Color(0xFF111827);

  // Dark mode equivalents
  static const darkSurface = Color(0xFF1A1A2E);
  static const darkCard = Color(0xFF222244);
  static const darkBorder = Color(0xFF2D2D4A);
  static const darkInputBg = Color(0xFF2A2A45);
}

ThemeData appThemeLight() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    colorScheme: ColorScheme.light(
      primary: AppColors.teal,
      onPrimary: Colors.white,
      surface: Colors.white,
      onSurface: AppColors.gray900,
    ),
    scaffoldBackgroundColor: AppColors.paper,
    fontFamily: '.SF Pro Display',
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.paperSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
    ),
  );
}

ThemeData appThemeDark() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: ColorScheme.dark(
      primary: AppColors.teal,
      onPrimary: Colors.white,
      surface: AppColors.darkSurface,
      onSurface: Colors.white,
    ),
    scaffoldBackgroundColor: AppColors.darkSurface,
    fontFamily: '.SF Pro Display',
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.darkSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
    ),
  );
}

/// Helper extension to get adaptive colors based on brightness
extension AppColorsX on BuildContext {
  bool get isDark => Theme.of(this).brightness == Brightness.dark;

  Color get surfaceColor => isDark ? AppColors.darkSurface : AppColors.paperSurface;
  Color get cardColor => isDark ? AppColors.darkCard : Colors.white;
  Color get screenBg => isDark ? const Color(0xFF12122A) : AppColors.paper;
  Color get borderColor => isDark ? AppColors.darkBorder : AppColors.gray100;
  Color get inputBg => isDark ? AppColors.darkInputBg : Colors.white;
  Color get inputBorder => isDark ? AppColors.darkBorder : AppColors.gray200;
  Color get textPrimary => isDark ? Colors.white : AppColors.gray900;
  Color get textSecondary => isDark ? const Color(0xFFB0B0CC) : AppColors.gray600;
  Color get textMuted => isDark ? const Color(0xFF7070A0) : AppColors.gray400;
  Color get chipBg => isDark ? AppColors.darkBorder : AppColors.gray100;
  Color get chipText => isDark ? const Color(0xFFB0B0CC) : AppColors.gray600;
  Color get chipIcon => isDark ? const Color(0xFF7070A0) : AppColors.gray400;
  Color get tealLightAdaptive => isDark ? const Color(0xFF1A3D30) : AppColors.tealLight;
  Color get tealDarkAdaptive => isDark ? const Color(0xFF4AE0A8) : AppColors.tealDark;
  Color get amberLightAdaptive => isDark ? const Color(0xFF3D3020) : AppColors.amberLight;
  Color get shadowColor => isDark ? Colors.black.withValues(alpha: 0.3) : Colors.black.withValues(alpha: 0.06);
}
