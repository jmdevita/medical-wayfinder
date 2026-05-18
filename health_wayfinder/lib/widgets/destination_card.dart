import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/facility.dart';

class DestinationCard extends StatelessWidget {
  final Department department;
  final VoidCallback onShowTheWay;

  const DestinationCard({
    super.key,
    required this.department,
    required this.onShowTheWay,
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
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  AppLocalizations.of(context)!.destinationLabel,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: AppColors.teal,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  department.name,
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: context.textPrimary,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    _Chip(
                      icon: Icons.local_hospital,
                      label: department.building,
                    ),
                    if (department.floor.trim().isNotEmpty)
                      _Chip(
                        icon: Icons.layers,
                        label: department.floor,
                      ),
                    if (department.accessible)
                      _Chip(
                        icon: Icons.accessible,
                        label: AppLocalizations.of(context)!.accessible,
                        isAccessible: true,
                      ),
                  ],
                ),
                if (department.hours != null) ...[
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Icon(Icons.schedule, size: 14, color: context.textMuted),
                      const SizedBox(width: 5),
                      Text(
                        department.hours!,
                        style: TextStyle(
                          fontSize: 13,
                          color: context.textMuted,
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          Container(
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: context.borderColor)),
            ),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: onShowTheWay,
                child: Container(
                  height: 52,
                  alignment: Alignment.center,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.directions_walk, size: 18, color: AppColors.teal),
                      const SizedBox(width: 8),
                      Text(
                        AppLocalizations.of(context)!.showMeTheWay,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: AppColors.teal,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isAccessible;

  const _Chip({
    required this.icon,
    required this.label,
    this.isAccessible = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(
        color: isAccessible ? context.tealLightAdaptive : context.chipBg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 14,
            color: isAccessible ? AppColors.teal : context.chipIcon,
          ),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: isAccessible ? context.tealDarkAdaptive : context.chipText,
            ),
          ),
        ],
      ),
    );
  }
}
