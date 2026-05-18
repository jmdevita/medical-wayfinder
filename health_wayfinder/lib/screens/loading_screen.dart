import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/facility.dart';
import '../widgets/facility_bar.dart';
import '../widgets/user_bubble.dart';

class LoadingScreen extends StatefulWidget {
  final Facility facility;
  final String query;
  final bool locating;

  const LoadingScreen({
    super.key,
    required this.facility,
    required this.query,
    this.locating = false,
  });

  @override
  State<LoadingScreen> createState() => _LoadingScreenState();
}

class _LoadingScreenState extends State<LoadingScreen>
    with TickerProviderStateMixin {
  late List<AnimationController> _controllers;

  @override
  void initState() {
    super.initState();
    _controllers = List.generate(3, (i) {
      return AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1200),
      );
    });
    // Stagger the animations
    _controllers[0].repeat();
    Future.delayed(const Duration(milliseconds: 150), () {
      if (mounted) _controllers[1].repeat();
    });
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) _controllers[2].repeat();
    });
  }

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: context.screenBg,
      child: Column(
        children: [
          FacilityBar(
            facility: widget.facility,
            showChevron: false,
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  UserBubble(text: widget.query),
                  const SizedBox(height: 32),
                  Center(
                    child: Column(
                      children: [
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: List.generate(3, (i) {
                            return AnimatedBuilder(
                              animation: _controllers[i],
                              builder: (_, _) {
                                final value = _controllers[i].value;
                                final scale = value < 0.5
                                    ? 0.6 + 0.4 * (value * 2)
                                    : 1.0 - 0.4 * ((value - 0.5) * 2);
                                final opacity = value < 0.5
                                    ? 0.4 + 0.6 * (value * 2)
                                    : 1.0 - 0.6 * ((value - 0.5) * 2);
                                return Padding(
                                  padding:
                                      const EdgeInsets.symmetric(horizontal: 4),
                                  child: Transform.scale(
                                    scale: scale,
                                    child: Opacity(
                                      opacity: opacity,
                                      child: Container(
                                        width: 10,
                                        height: 10,
                                        decoration: const BoxDecoration(
                                          color: AppColors.teal,
                                          shape: BoxShape.circle,
                                        ),
                                      ),
                                    ),
                                  ),
                                );
                              },
                            );
                          }),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          widget.locating
                              ? AppLocalizations.of(context)!.locatingYou
                              : AppLocalizations.of(context)!.findingDestination,
                          style:
                              TextStyle(fontSize: 15, color: context.textMuted),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
