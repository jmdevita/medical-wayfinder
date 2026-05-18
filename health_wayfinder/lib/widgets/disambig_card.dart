import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/facility.dart';

class DisambigCard extends StatelessWidget {
  final String question;
  final List<Department> options;
  final ValueChanged<Department> onSelected;

  const DisambigCard({
    super.key,
    required this.question,
    required this.options,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: context.cardColor,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: context.shadowColor,
            blurRadius: 6,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  AppLocalizations.of(context)!.whichOne,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: AppColors.teal,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  question,
                  style: TextStyle(
                    fontSize: 17,
                    fontFamily: 'Georgia',
                    fontStyle: FontStyle.italic,
                    color: context.textPrimary,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
            child: Column(
              children: [
                for (var i = 0; i < options.length; i++) ...[
                  if (i > 0) const SizedBox(height: 10),
                  _DisambigOption(
                    department: options[i],
                    highlighted: i == 0,
                    onTap: () => onSelected(options[i]),
                  ),
                ],
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: context.borderColor)),
            ),
            child: Text(
              AppLocalizations.of(context)!.disambigFallback,
              style: TextStyle(fontSize: 14, color: context.textMuted),
            ),
          ),
        ],
      ),
    );
  }
}

class _DisambigOption extends StatelessWidget {
  final Department department;
  final bool highlighted;
  final VoidCallback onTap;

  const _DisambigOption({
    required this.department,
    required this.onTap,
    this.highlighted = false,
  });

  @override
  Widget build(BuildContext context) {
    final hasSubtitle =
        department.building.isNotEmpty || department.floor.isNotEmpty;
    final subtitle = [
      if (department.building.isNotEmpty) department.building,
      if (department.floor.isNotEmpty) department.floor,
    ].join(' · ');

    final borderColor =
        highlighted ? AppColors.amber : context.borderColor;
    final fillColor =
        highlighted ? context.amberLightAdaptive : Colors.transparent;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
          decoration: BoxDecoration(
            color: fillColor,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: borderColor, width: 1.2),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                department.name,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: context.textPrimary,
                  height: 1.2,
                ),
              ),
              if (hasSubtitle) ...[
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: 12,
                    color: context.textMuted,
                    height: 1.2,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
