import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_wayfinder/models/topology.dart';

void main() {
  group('CampusGraph.fromJson', () {
    late CampusGraph kaiser;
    late CampusGraph jp;

    setUpAll(() {
      kaiser = _loadGraph('assets/facilities/kaiser_panorama_city.topology.json');
      jp = _loadGraph('assets/facilities/southern_jp.topology.json');
    });

    test('parses Kaiser topology with expected scale', () {
      expect(kaiser.facilityId, 'kaiser_panorama_city');
      expect(kaiser.nodes.length, greaterThanOrEqualTo(20));
      // Sanity: every adjacency entry references an existing node.
      for (final entry in kaiser.adjacency.entries) {
        expect(kaiser.nodes.containsKey(entry.key), isTrue,
            reason: 'edge "from" ${entry.key} not in nodes');
        for (final edge in entry.value) {
          expect(kaiser.nodes.containsKey(edge.to), isTrue,
              reason: 'edge "to" ${edge.to} not in nodes');
        }
      }
    });

    test('Kaiser cantara_parking has outgoing edges', () {
      final edges = kaiser.adjacency['cantara_parking'] ?? const [];
      expect(edges, isNotEmpty);
      // At least one edge should mention "campus" or a specific building.
      expect(
        edges.any((e) =>
            e.instruction.toLowerCase().contains('campus') ||
            e.instruction.toLowerCase().contains('building')),
        isTrue,
      );
    });

    test('nodeById returns node and null for unknowns', () {
      expect(kaiser.nodeById('building_5_entrance'), isNotNull);
      expect(kaiser.nodeById('building_5_entrance')!.type, NodeType.entrance);
      expect(kaiser.nodeById('does_not_exist'), isNull);
    });

    test('parses JP topology', () {
      expect(jp.facilityId, 'southern_jp');
      expect(jp.nodes.length, greaterThanOrEqualTo(8));
      expect(jp.nodeById('main_entrance'), isNotNull);
    });

    test('TopologyEdge.cost falls back when distance is missing', () {
      final edge = TopologyEdge.fromJson({
        'from': 'a',
        'to': 'b',
        'walk_minutes': 2.0,
        'instruction': 'x',
      });
      expect(edge.distanceMeters, 0);
      expect(edge.cost, 160); // 2 * 80
    });
  });

  group('haversineMeters', () {
    test('returns ~0 for the same point', () {
      expect(haversineMeters(34.0, -118.0, 34.0, -118.0), closeTo(0, 0.01));
    });

    test('matches a known short distance', () {
      // ~1 degree of latitude ≈ 111 km.
      final m = haversineMeters(34.0, -118.0, 34.001, -118.0);
      expect(m, closeTo(111, 5));
    });
  });
}

CampusGraph _loadGraph(String relPath) {
  final file = File(relPath);
  final str = file.readAsStringSync();
  return CampusGraph.fromJson(json.decode(str) as Map<String, dynamic>);
}
