import 'package:flutter/material.dart';
import '../theme.dart';

class MicButton extends StatelessWidget {
  final VoidCallback onPressed;
  final double size;
  final Color? color;
  final Color? iconColor;

  const MicButton({
    super.key,
    required this.onPressed,
    this.size = 80,
    this.color,
    this.iconColor,
  });

  /// Large primary mic button (home screen, directions screen)
  const MicButton.large({
    super.key,
    required this.onPressed,
  })  : size = 80,
        color = AppColors.teal,
        iconColor = Colors.white;

  /// Medium mic button (directions follow-up, walking help)
  const MicButton.medium({
    super.key,
    required this.onPressed,
  })  : size = 64,
        color = AppColors.teal,
        iconColor = Colors.white;

  /// Help mic button (walking mode - white with border)
  const MicButton.help({
    super.key,
    required this.onPressed,
  })  : size = 64,
        color = Colors.white,
        iconColor = AppColors.gray400;

  /// Small mic button (input bars)
  const MicButton.small({
    super.key,
    required this.onPressed,
  })  : size = 44,
        color = AppColors.teal,
        iconColor = Colors.white;

  @override
  Widget build(BuildContext context) {
    final bgColor = color ?? AppColors.teal;
    final icColor = iconColor ?? Colors.white;
    final iconSize = size * 0.375;

    return GestureDetector(
      onTap: onPressed,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: bgColor,
          shape: BoxShape.circle,
          border: bgColor == Colors.white
              ? Border.all(color: AppColors.gray200, width: 2)
              : null,
          boxShadow: bgColor == AppColors.teal
              ? [
                  BoxShadow(
                    color: AppColors.teal.withValues(alpha: 0.3),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  )
                ]
              : [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 10,
                    offset: const Offset(0, 2),
                  )
                ],
        ),
        child: Icon(Icons.mic, size: iconSize, color: icColor),
      ),
    );
  }
}
