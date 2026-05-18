import 'facility.dart';
import 'step.dart';
import 'topology.dart';

enum GuideMessageType {
  userQuery,
  destinationCard,
  disambigCard,
  stepCarousel,
  guideText,
  arrival,
}

class GuideMessage {
  final String id;
  final GuideMessageType type;
  final String? text;
  final Department? department;
  final List<Department>? options;
  final List<WalkingStep>? steps;
  /// Underlying topology route the carousel was built from. When present,
  /// the step card renders an offline mini-map showing the route polyline +
  /// building footprints. Null for prose-derived steps.
  final List<RouteStep>? route;
  final CampusGraph? graph;
  final String? checkInText;
  final bool isPlaceholder;
  final DateTime timestamp;

  GuideMessage({
    required this.type,
    this.text,
    this.department,
    this.options,
    this.steps,
    this.route,
    this.graph,
    this.checkInText,
    this.isPlaceholder = false,
  })  : id = '${type.name}_${DateTime.now().millisecondsSinceEpoch}',
        timestamp = DateTime.now();

  factory GuideMessage.userQuery(String text) =>
      GuideMessage(type: GuideMessageType.userQuery, text: text);

  factory GuideMessage.destination(Department dept) =>
      GuideMessage(type: GuideMessageType.destinationCard, department: dept);

  factory GuideMessage.disambig(List<Department> options, {String? question}) =>
      GuideMessage(
        type: GuideMessageType.disambigCard,
        options: options,
        text: question,
      );

  factory GuideMessage.steps(
    List<WalkingStep> steps, {
    List<RouteStep>? route,
    CampusGraph? graph,
  }) =>
      GuideMessage(
        type: GuideMessageType.stepCarousel,
        steps: steps,
        route: route,
        graph: graph,
      );

  factory GuideMessage.guideText(String text) =>
      GuideMessage(type: GuideMessageType.guideText, text: text);

  factory GuideMessage.thinking(String text) => GuideMessage(
        type: GuideMessageType.guideText,
        text: text,
        isPlaceholder: true,
      );

  factory GuideMessage.arrival({required String checkInText}) =>
      GuideMessage(type: GuideMessageType.arrival, checkInText: checkInText);
}
