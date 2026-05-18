import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';

class WalkingProgressBar extends StatelessWidget {
  final int current;
  final int total;

  const WalkingProgressBar({
    super.key,
    required this.current,
    required this.total,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: LinearProgressIndicator(
              value: total > 0 ? current / total : 0,
              minHeight: 4,
              backgroundColor: context.chipBg,
              valueColor: const AlwaysStoppedAnimation(AppColors.teal),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Text(
          AppLocalizations.of(context)!.progressFormat(current, total),
          style: TextStyle(fontSize: 13, color: context.textMuted),
        ),
      ],
    );
  }
}
