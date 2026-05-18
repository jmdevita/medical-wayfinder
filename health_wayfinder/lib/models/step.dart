class WalkingStep {
  final int number;
  final String text;
  final String? accessibilityBadge;
  /// Index into the RouteStep list this WalkingStep was split from. A single
  /// edge can produce several WalkingSteps; they share the same routeIndex
  /// so the mini-map can highlight the correct edge while a sub-step is
  /// active. Null when the step didn't originate from a topology route
  /// (e.g. fallback prose parsing).
  final int? routeIndex;

  const WalkingStep({
    required this.number,
    required this.text,
    this.accessibilityBadge,
    this.routeIndex,
  });
}
