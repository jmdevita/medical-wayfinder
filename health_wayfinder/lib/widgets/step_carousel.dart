import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/step.dart';
import '../models/topology.dart';
import '../services/speech_service.dart';
import 'route_mini_map.dart';

class StepCarousel extends StatefulWidget {
  final List<WalkingStep> steps;
  final List<RouteStep>? route;
  final CampusGraph? graph;

  const StepCarousel({
    super.key,
    required this.steps,
    this.route,
    this.graph,
  });

  @override
  State<StepCarousel> createState() => _StepCarouselState();
}

class _StepCarouselState extends State<StepCarousel> {
  late PageController _pageController;
  final _speech = SpeechService.instance;
  int _currentPage = 0;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    // Speak first step after build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.steps.isNotEmpty) _speakStep(0);
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _speakStep(int index) {
    if (index < 0 || index >= widget.steps.length) return;
    final step = widget.steps[index];
    final isLast = index == widget.steps.length - 1;
    final text = _speech.buildStepText(
      stepNumber: step.number,
      instruction: step.text,
      accessibilityBadge: step.accessibilityBadge,
      isLastStep: isLast,
    );
    _speech.stopSpeaking();
    _speech.speakAsync(text);
  }

  bool get _hasMiniMap =>
      widget.graph != null &&
      widget.route != null &&
      widget.route!.isNotEmpty &&
      !widget.graph!.osm.isEmpty;

  Widget _stepVisual({
    required BuildContext context,
    required int index,
    required int totalSteps,
    required WalkingStep step,
  }) {
    if (_hasMiniMap) {
      // Active edge highlight: prefer the WalkingStep's own routeIndex
      // (multiple sub-steps can share an edge); fall back to the carousel
      // index when the splitter didn't tag one (e.g. prose fallback).
      final activeIdx = step.routeIndex ?? index;
      return SizedBox(
        height: 150,
        child: RouteMiniMap(
          graph: widget.graph!,
          route: widget.route!,
          activeEdgeIndex: activeIdx,
        ),
      );
    }
    return SizedBox(
      height: 64,
      child: CustomPaint(
        painter: _StepPathPainter(
          currentIndex: index,
          totalSteps: totalSteps,
          pathColor: AppColors.amber,
          dotColor: AppColors.teal,
          trackColor: context.borderColor,
        ),
        size: Size.infinite,
      ),
    );
  }

  void _onPageChanged(int page) {
    setState(() => _currentPage = page);
    // Stop any in-progress speech but don't auto-speak the new step.
    // Swiping is a deliberate read action — TTS on every swipe is noise.
    // The first step is still auto-spoken on appearance via initState;
    // the global header mute toggle controls everything beyond that.
    _speech.stopSpeaking();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.steps.isEmpty) return const SizedBox.shrink();

    final l10n = AppLocalizations.of(context)!;
    final headerLabel = l10n
        .progressFormat(_currentPage + 1, widget.steps.length)
        .toUpperCase();

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 0, 8, 10),
          child: Row(
            children: [
              Text(
                headerLabel,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: AppColors.teal,
                  letterSpacing: 1.2,
                ),
              ),
              const Spacer(),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(widget.steps.length, (index) {
                  return Container(
                    width: 7,
                    height: 7,
                    margin: const EdgeInsets.symmetric(horizontal: 2.5),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: index == _currentPage
                          ? AppColors.teal
                          : context.chipBg,
                    ),
                  );
                }),
              ),
            ],
          ),
        ),
        SizedBox(
          height: _hasMiniMap ? 360 : 290,
          child: PageView.builder(
            controller: _pageController,
            itemCount: widget.steps.length,
            onPageChanged: _onPageChanged,
            itemBuilder: (context, index) {
              final step = widget.steps[index];
              final isLast = index == widget.steps.length - 1;
              final totalSteps = widget.steps.length;
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Container(
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
                  // SingleChildScrollView + ConstrainedBox + Center:
                  // short steps stay vertically centered (Center fills
                  // the minHeight), long steps become scrollable inside
                  // the card so we never overflow the parent SizedBox.
                  // We avoid IntrinsicHeight here because every PageView
                  // swipe relayouts the subtree (which includes a
                  // FlutterMap) twice — once for intrinsic measurement
                  // and once for final layout.
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      return SingleChildScrollView(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        child: ConstrainedBox(
                          constraints:
                              BoxConstraints(minHeight: constraints.maxHeight - 32),
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Padding(
                                  padding: const EdgeInsets.fromLTRB(
                                      14, 0, 14, 14),
                                  child: _stepVisual(
                                    context: context,
                                    index: index,
                                    totalSteps: totalSteps,
                                    step: step,
                                  ),
                                ),
                                Padding(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 24),
                                  child: Text(
                                    step.text,
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w600,
                                      color: context.textPrimary,
                                      height: 1.35,
                                    ),
                                  ),
                                ),
                                if (step.accessibilityBadge != null) ...[
                                  const SizedBox(height: 12),
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 14,
                                      vertical: 5,
                                    ),
                                    decoration: BoxDecoration(
                                      color: context.tealLightAdaptive,
                                      borderRadius: BorderRadius.circular(999),
                                    ),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(
                                          isLast
                                              ? Icons.check
                                              : Icons.accessible,
                                          size: 16,
                                          color: context.tealDarkAdaptive,
                                        ),
                                        const SizedBox(width: 6),
                                        Text(
                                          step.accessibilityBadge!,
                                          style: TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w600,
                                            color: context.tealDarkAdaptive,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _StepPathPainter extends CustomPainter {
  final int currentIndex;
  final int totalSteps;
  final Color pathColor;
  final Color dotColor;
  final Color trackColor;

  _StepPathPainter({
    required this.currentIndex,
    required this.totalSteps,
    required this.pathColor,
    required this.dotColor,
    required this.trackColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final track = Paint()
      ..color = trackColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;

    final progress = Paint()
      ..color = pathColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.6
      ..strokeCap = StrokeCap.round;

    // Curved path that arcs gently across the card.
    final start = Offset(size.width * 0.08, size.height * 0.78);
    final end = Offset(size.width * 0.92, size.height * 0.32);
    final c1 = Offset(size.width * 0.32, size.height * 0.10);
    final c2 = Offset(size.width * 0.68, size.height * 0.95);

    final fullPath = Path()
      ..moveTo(start.dx, start.dy)
      ..cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, end.dx, end.dy);
    canvas.drawPath(fullPath, track);

    // Highlight portion up to current step.
    final t = totalSteps <= 1
        ? 1.0
        : ((currentIndex + 1) / totalSteps).clamp(0.0, 1.0);
    final metrics = fullPath.computeMetrics().first;
    final highlight = metrics.extractPath(0, metrics.length * t);
    canvas.drawPath(highlight, progress);

    // Endpoint dot (start) — neutral
    final neutralDot = Paint()..color = trackColor;
    canvas.drawCircle(start, 4, neutralDot);

    // Current waypoint dot
    final point = metrics.getTangentForOffset(metrics.length * t)?.position;
    if (point != null) {
      final outer = Paint()..color = dotColor.withValues(alpha: 0.18);
      final inner = Paint()..color = dotColor;
      canvas.drawCircle(point, 9, outer);
      canvas.drawCircle(point, 4.5, inner);
    }
  }

  @override
  bool shouldRepaint(covariant _StepPathPainter old) =>
      old.currentIndex != currentIndex ||
      old.totalSteps != totalSteps ||
      old.pathColor != pathColor ||
      old.dotColor != dotColor ||
      old.trackColor != trackColor;
}
