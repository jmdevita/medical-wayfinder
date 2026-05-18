import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/facility.dart';
import '../widgets/facility_bar.dart';
import '../widgets/facility_picker.dart';

class HomeScreen extends StatefulWidget {
  final Facility facility;
  final List<Facility> facilities;
  final bool bootstrapFailed;
  final ValueChanged<Facility> onFacilityChanged;
  final ValueChanged<String> onQuery;
  final FocusNode textFocusNode;
  final bool needsAccessibility;
  final ValueChanged<bool> onAccessibilityChanged;

  const HomeScreen({
    super.key,
    required this.facility,
    required this.facilities,
    required this.onFacilityChanged,
    required this.onQuery,
    required this.textFocusNode,
    required this.needsAccessibility,
    required this.onAccessibilityChanged,
    this.bootstrapFailed = false,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _textController = TextEditingController();

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    if (widget.bootstrapFailed) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.error_outline, size: 48, color: context.textMuted),
              const SizedBox(height: 16),
              Text(
                l10n.noFacilitiesTitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  color: context.textPrimary,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                l10n.noFacilitiesBody,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 15, color: context.textMuted),
              ),
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
        FacilityBar(
          facility: widget.facility,
          onTap: () async {
            final result = await FacilityPicker.show(
              context,
              facilities: widget.facilities,
              selected: widget.facility,
            );
            if (result != null) widget.onFacilityChanged(result);
          },
        ),
        Expanded(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                l10n.homeTitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w700,
                  color: context.textPrimary,
                  height: 1.25,
                ),
              ),
              // Space for the floating mic button overlay
              const SizedBox(height: 140),
            ],
          ),
        ),
        // Accessibility toggle
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
          child: GestureDetector(
            onTap: () => widget.onAccessibilityChanged(!widget.needsAccessibility),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: widget.needsAccessibility
                    ? context.tealLightAdaptive
                    : context.chipBg,
                borderRadius: BorderRadius.circular(999),
                border: Border.all(
                  color: widget.needsAccessibility
                      ? AppColors.teal
                      : context.inputBorder,
                  width: 1.5,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.accessible,
                    size: 16,
                    color: widget.needsAccessibility
                        ? AppColors.teal
                        : context.textMuted,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    l10n.accessibilityToggle,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: widget.needsAccessibility
                          ? context.tealDarkAdaptive
                          : context.textMuted,
                    ),
                  ),
                  if (widget.needsAccessibility) ...[
                    const SizedBox(width: 6),
                    Icon(Icons.check, size: 14, color: AppColors.teal),
                  ],
                ],
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 40),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _textController,
                  focusNode: widget.textFocusNode,
                  textInputAction: TextInputAction.send,
                  decoration: InputDecoration(
                    hintText: l10n.homeTextPlaceholder,
                    hintStyle: TextStyle(color: context.textMuted),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(999),
                      borderSide: BorderSide(color: context.inputBorder, width: 1.5),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(999),
                      borderSide: BorderSide(color: context.inputBorder, width: 1.5),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(999),
                      borderSide: const BorderSide(color: AppColors.teal, width: 1.5),
                    ),
                  ),
                  onSubmitted: (text) {
                    if (text.trim().isNotEmpty) {
                      // Dismiss the keyboard immediately so it doesn't sit
                      // on screen during model prefill (which can take
                      // several seconds on device and makes the keyboard
                      // look frozen).
                      widget.textFocusNode.unfocus();
                      _textController.clear();
                      widget.onQuery(text.trim());
                    }
                  },
                ),
              ),
              const SizedBox(width: 10),
              Semantics(
                button: true,
                label: l10n.a11ySendQuery,
                child: GestureDetector(
                  onTap: () {
                    final text = _textController.text.trim();
                    if (text.isNotEmpty) {
                      // Dismiss the keyboard immediately on Send so it
                      // doesn't sit on screen during model prefill.
                      widget.textFocusNode.unfocus();
                      _textController.clear();
                      widget.onQuery(text);
                    }
                  },
                  child: Container(
                    width: 48,
                    height: 48,
                    decoration: const BoxDecoration(
                      color: AppColors.teal,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.send, size: 20, color: Colors.white),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
