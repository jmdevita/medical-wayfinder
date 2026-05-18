import '../l10n/generated/app_localizations.dart';
import '../models/step.dart';
import '../models/topology.dart';

/// Convert orchestrator [RouteStep]s into UI [WalkingStep]s for the carousel.
///
/// Each route edge's instruction is split at sentence and em-dash
/// boundaries so a single-edge topology route still produces a multi-step
/// carousel (matches the behavior of the prose `_parseDirectionsToSteps`
/// fallback). Step numbers increment across sub-steps so the user sees
/// "Step 1 of 4" instead of "Step 1 of 1" for a verbose single-edge route.
///
/// Badge rules:
/// - The very last sub-step of the very last edge gets the arrival badge.
/// - When [needsAccessibility] is true, any sub-step that mentions an
///   elevator, ramp, automatic doors, or "accessible" gets the
///   accessibility badge (overridden by arrival on the final sub-step).
List<WalkingStep> routeToSteps(
  List<RouteStep> route, {
  required bool needsAccessibility,
  AppLocalizations? l10n,
}) {
  final steps = <WalkingStep>[];
  var stepNumber = 1;
  for (var i = 0; i < route.length; i++) {
    final isLastEdge = i == route.length - 1;
    final subInstructions = _splitInstruction(route[i].instruction);
    for (var j = 0; j < subInstructions.length; j++) {
      final isLastSub = j == subInstructions.length - 1;
      final isFinal = isLastEdge && isLastSub;
      final text = subInstructions[j];
      String? badge;
      final lower = text.toLowerCase();
      if (needsAccessibility &&
          (lower.contains('elevator') ||
              (lower.contains('automatic') && lower.contains('door')) ||
              lower.contains('ramp') ||
              lower.contains('accessible'))) {
        badge = l10n?.accessible ?? 'Accessible';
      }
      if (isFinal) badge = l10n?.youveArrived ?? "You've arrived";
      steps.add(WalkingStep(
        number: stepNumber++,
        text: text,
        accessibilityBadge: badge,
        routeIndex: i,
      ));
    }
  }
  return steps;
}

/// Break a long instruction into action-sized sub-steps. Splits on
/// sentence boundaries (".\s") and em-dash (" — "). Does NOT split on
/// commas because authored landmark instructions often contain comma-
/// separated lists ("the post office, pharmacy, and lab") that should
/// stay together. Trims trailing periods so steps don't end inconsistently.
List<String> _splitInstruction(String instruction) {
  final parts = instruction
      .split(RegExp(r'\s+—\s+|\.\s+'))
      .map((s) => s.trim().replaceAll(RegExp(r'\.$'), ''))
      .where((s) => s.isNotEmpty)
      .toList();
  return parts.isEmpty ? [instruction] : parts;
}
