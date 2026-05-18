import 'package:flutter/material.dart';
import '../theme.dart';

/// Bridges the iOS LaunchScreen.storyboard handoff. Renders the same
/// explore-icon + "Medical Wayfinder" wordmark composition on white, so the
/// transition from the native launch screen to Flutter is visually
/// continuous instead of cutting to a half-built home screen while
/// facility discovery resolves.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.white,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.explore, size: 120, color: AppColors.teal),
            const SizedBox(height: 24),
            Text(
              'Medical Wayfinder',
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w600,
                color: AppColors.teal,
                letterSpacing: -0.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
