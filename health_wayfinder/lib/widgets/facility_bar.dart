import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/facility.dart';

class FacilityBar extends StatelessWidget {
  final Facility facility;
  final VoidCallback? onTap;
  final bool showChevron;
  final bool showAddress;

  const FacilityBar({
    super.key,
    required this.facility,
    this.onTap,
    this.showChevron = true,
    this.showAddress = true,
  });

  @override
  Widget build(BuildContext context) {
    final topPadding = MediaQuery.of(context).padding.top;
    final l10n = AppLocalizations.of(context);
    return Semantics(
      button: onTap != null,
      label: onTap != null
          ? '${facility.name}. ${l10n?.a11yChangeFacility ?? 'Change facility'}'
          : facility.name,
      child: GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.fromLTRB(24, 14 + topPadding, 24, 14),
        decoration: BoxDecoration(
          color: context.surfaceColor,
          border: Border(
            bottom: BorderSide(color: context.borderColor),
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: context.tealLightAdaptive,
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.location_on,
                size: 18,
                color: AppColors.teal,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    facility.name,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: context.textPrimary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (showAddress)
                    Text(
                      facility.address,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        color: context.textMuted,
                      ),
                    ),
                ],
              ),
            ),
            if (showChevron)
              Icon(
                Icons.arrow_drop_down,
                size: 20,
                color: context.textMuted,
              ),
          ],
        ),
      ),
      ),
    );
  }
}

