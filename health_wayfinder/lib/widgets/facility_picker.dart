import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/facility.dart';

class FacilityPicker extends StatelessWidget {
  final List<Facility> facilities;
  final Facility? selected;
  final ValueChanged<Facility> onSelected;

  const FacilityPicker({
    super.key,
    required this.facilities,
    this.selected,
    required this.onSelected,
  });

  static Future<Facility?> show(
    BuildContext context, {
    required List<Facility> facilities,
    Facility? selected,
  }) {
    return showModalBottomSheet<Facility>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => FacilityPicker(
        facilities: facilities,
        selected: selected,
        onSelected: (f) => Navigator.pop(context, f),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.75,
      decoration: BoxDecoration(
        color: context.cardColor,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          const SizedBox(height: 10),
          Container(
            width: 36,
            height: 4,
            decoration: BoxDecoration(
              color: AppColors.gray300,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  AppLocalizations.of(context)!.facilityPickerTitle,
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: context.textPrimary),
                ),
                GestureDetector(
                  onTap: () => Navigator.pop(context),
                  child: Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      color: context.chipBg,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(Icons.close, size: 16, color: context.textMuted),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: TextField(
              decoration: InputDecoration(
                hintText: AppLocalizations.of(context)!.facilityPickerSearch,
                hintStyle: TextStyle(color: context.textMuted),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: context.inputBorder, width: 1.5),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: context.inputBorder, width: 1.5),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: AppColors.teal, width: 1.5),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          _SectionLabel(AppLocalizations.of(context)!.facilityPickerNearby),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.only(bottom: 40),
              itemCount: facilities.length,
              itemBuilder: (context, index) {
                final facility = facilities[index];
                final isSelected = facility.id == selected?.id;
                return _FacilityItem(
                  facility: facility,
                  isSelected: isSelected,
                  onTap: () => onSelected(facility),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 12, 24, 6),
      child: Text(
        text.toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: context.textMuted,
          letterSpacing: 0.6,
        ),
      ),
    );
  }
}

class _FacilityItem extends StatelessWidget {
  final Facility facility;
  final bool isSelected;
  final VoidCallback onTap;

  const _FacilityItem({
    required this.facility,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        color: isSelected ? context.tealLightAdaptive : Colors.transparent,
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: isSelected ? context.tealLightAdaptive : context.chipBg,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(
                Icons.local_hospital,
                size: 20,
                color: isSelected ? AppColors.teal : context.textMuted,
              ),
            ),
            const SizedBox(width: 12),
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
                  ),
                  Text(
                    facility.type,
                    style: TextStyle(
                      fontSize: 12,
                      color: context.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            if (facility.distanceMiles != null)
              Text(
                '${facility.distanceMiles} mi',
                style: TextStyle(fontSize: 12, color: context.textMuted),
              ),
            if (isSelected) ...[
              const SizedBox(width: 8),
              const Icon(Icons.check, size: 20, color: AppColors.teal),
            ],
          ],
        ),
      ),
    );
  }
}
