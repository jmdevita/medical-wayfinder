import 'package:flutter_test/flutter_test.dart';
import 'package:health_wayfinder/models/topology.dart';
import 'package:health_wayfinder/services/route_steps.dart';

TopologyNode _node(String id, String label) => TopologyNode(
      id: id,
      type: NodeType.entrance,
      label: label,
      description: '',
    );

RouteStep _step(String from, String to, String text) => RouteStep(
      from: _node(from, from),
      to: _node(to, to),
      instruction: text,
      distanceMeters: 50,
    );

void main() {
  group('routeToSteps', () {
    test('numbers steps from 1 and uses instruction text verbatim', () {
      final route = [
        _step('parking', 'b3', 'Walk to Building 3'),
        _step('b3', 'b3_basement', 'Take elevator down'),
      ];
      final steps = routeToSteps(route, needsAccessibility: false);
      expect(steps.length, 2);
      expect(steps[0].number, 1);
      expect(steps[0].text, 'Walk to Building 3');
      expect(steps[1].number, 2);
      expect(steps[1].text, 'Take elevator down');
    });

    test('last step gets arrival badge', () {
      final route = [
        _step('a', 'b', 'first'),
        _step('b', 'c', 'last'),
      ];
      final steps = routeToSteps(route, needsAccessibility: false);
      expect(steps[0].accessibilityBadge, isNull);
      expect(steps[1].accessibilityBadge, "You've arrived");
    });

    test('accessibility badge added when needed and instruction matches', () {
      final route = [
        _step('a', 'b', 'Walk past Building 4'),
        _step('b', 'c', 'Take the elevator to floor 3'),
        _step('c', 'd', 'Arrive at the lab'),
      ];
      final steps = routeToSteps(route, needsAccessibility: true);
      expect(steps[0].accessibilityBadge, isNull); // no a11y keyword
      expect(steps[1].accessibilityBadge, 'Accessible'); // elevator
      expect(steps[2].accessibilityBadge, "You've arrived"); // last wins
    });

    test('accessibility badge skipped when needsAccessibility false', () {
      final route = [
        _step('a', 'b', 'Take the elevator to floor 3'),
        _step('b', 'c', 'arrived'),
      ];
      final steps = routeToSteps(route, needsAccessibility: false);
      expect(steps[0].accessibilityBadge, isNull);
    });

    test('empty route returns empty list', () {
      expect(routeToSteps(const [], needsAccessibility: false), isEmpty);
    });

    test('splits a single edge with em-dash into multiple steps', () {
      final route = [
        _step('parking', 'b6',
            'Exit Ventura parking toward Roscoe Blvd — Building 6 is directly ahead, look for the pharmacy and urgent care signs.'),
      ];
      final steps = routeToSteps(route, needsAccessibility: false);
      expect(steps.length, 2);
      expect(steps[0].text, 'Exit Ventura parking toward Roscoe Blvd');
      expect(steps[1].text,
          'Building 6 is directly ahead, look for the pharmacy and urgent care signs');
      expect(steps[0].number, 1);
      expect(steps[1].number, 2);
      // Final sub-step still gets the arrival badge.
      expect(steps[1].accessibilityBadge, "You've arrived");
    });

    test('splits on period+space across sentences', () {
      final route = [
        _step('a', 'b',
            'Walk to Building 3. Enter through the automatic glass doors. Take the elevator to the basement.'),
      ];
      final steps = routeToSteps(route, needsAccessibility: true);
      expect(steps.length, 3);
      expect(steps[0].text, 'Walk to Building 3');
      expect(steps[1].text, 'Enter through the automatic glass doors');
      expect(steps[2].text, 'Take the elevator to the basement');
      // Each sub-step gets its own badge based on its own keywords;
      // the final sub-step of the final edge gets arrival regardless.
      expect(steps[0].accessibilityBadge, isNull);
      expect(steps[1].accessibilityBadge, 'Accessible');
      expect(steps[2].accessibilityBadge, "You've arrived");
    });

    test('numbers continue across multi-edge routes with splits', () {
      final route = [
        _step('a', 'b', 'Walk to Building 3 — enter through glass doors.'),
        _step('b', 'c', 'Take elevator to basement. Lab is straight ahead.'),
      ];
      final steps = routeToSteps(route, needsAccessibility: false);
      // 2 sub-steps from edge 1 + 2 from edge 2 = 4 total.
      expect(steps.length, 4);
      expect(steps.map((s) => s.number), [1, 2, 3, 4]);
      expect(steps.last.accessibilityBadge, "You've arrived");
    });

    test('does not split on commas or "and"', () {
      final route = [
        _step('a', 'b',
            'Look for the post office, pharmacy, and lab on your right.'),
      ];
      final steps = routeToSteps(route, needsAccessibility: false);
      expect(steps.length, 1);
      expect(steps[0].text,
          'Look for the post office, pharmacy, and lab on your right');
    });
  });
}
