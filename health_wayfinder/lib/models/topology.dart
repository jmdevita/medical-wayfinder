import 'dart:math' as math;

enum NodeType { entrance, parking, landmark, junction, transit, floor }

NodeType _nodeTypeFrom(String s) {
  switch (s) {
    case 'entrance':
      return NodeType.entrance;
    case 'parking':
      return NodeType.parking;
    case 'landmark':
      return NodeType.landmark;
    case 'junction':
      return NodeType.junction;
    case 'transit':
      return NodeType.transit;
    case 'floor':
      return NodeType.floor;
    default:
      return NodeType.landmark;
  }
}

class TopologyNode {
  final String id;
  final NodeType type;
  final String label;
  final String description;
  final List<String> keywords;
  final double? lat;
  final double? lng;

  const TopologyNode({
    required this.id,
    required this.type,
    required this.label,
    required this.description,
    this.keywords = const [],
    this.lat,
    this.lng,
  });

  factory TopologyNode.fromJson(Map<String, dynamic> json) {
    return TopologyNode(
      id: json['id'] as String,
      type: _nodeTypeFrom((json['type'] as String?) ?? 'landmark'),
      label: (json['label'] as String?) ?? '',
      description: (json['description'] as String?) ?? '',
      keywords: (json['keywords'] as List<dynamic>?)
              ?.map((k) => k.toString())
              .toList() ??
          const [],
      lat: (json['lat'] as num?)?.toDouble(),
      lng: (json['lng'] as num?)?.toDouble(),
    );
  }
}

class TopologyEdge {
  final String from;
  final String to;
  final double distanceMeters;
  final double walkMinutes;
  final String instruction;
  final bool blocked;
  // Optional polyline tracing the actual walking path (lat,lng pairs). When
  // present the editor renders the real sidewalk geometry; routing still uses
  // distanceMeters which is summed along the polyline.
  final List<List<double>>? geometry;
  /// Structured accessibility tags authored in Atlas. Vocabulary mirrors the
  /// system prompt: `stairs` marks an edge as not wheelchair-passable; the
  /// rest are positive affordances surfaced as step badges.
  final List<String> accessibilityFeatures;

  const TopologyEdge({
    required this.from,
    required this.to,
    required this.distanceMeters,
    required this.walkMinutes,
    required this.instruction,
    this.blocked = false,
    this.geometry,
    this.accessibilityFeatures = const [],
  });

  factory TopologyEdge.fromJson(Map<String, dynamic> json) {
    final dist = (json['distance_meters'] as num?)?.toDouble() ?? 0;
    final mins = (json['walk_minutes'] as num?)?.toDouble() ?? 0;
    final geomRaw = json['geometry'] as List<dynamic>?;
    final geom = geomRaw
        ?.map((p) => (p as List<dynamic>)
            .map((c) => (c as num).toDouble())
            .toList())
        .toList();
    final feats = (json['accessibility_features'] as List<dynamic>?)
            ?.map((f) => f.toString())
            .toList() ??
        const <String>[];
    return TopologyEdge(
      from: json['from'] as String,
      to: json['to'] as String,
      distanceMeters: dist,
      walkMinutes: mins,
      instruction: (json['instruction'] as String?) ?? '',
      blocked: (json['blocked'] as bool?) ?? false,
      geometry: geom,
      accessibilityFeatures: feats,
    );
  }

  /// Cost used for routing. Falls back to walk_minutes scaled to meters
  /// when distance is missing, so edges without coords still rank sensibly.
  double get cost =>
      distanceMeters > 0 ? distanceMeters : walkMinutes * 80.0;

  /// True when this edge requires stairs (i.e. not wheelchair-passable).
  bool get requiresStairs => accessibilityFeatures.contains('stairs');
}

/// A baked OSM building footprint or amenity polygon. `polygon` is a closed
/// ring of [lat, lng] pairs in publish order.
class OsmFeature {
  final List<List<double>> polygon;
  final String? building;
  final String? amenity;
  final String? name;

  const OsmFeature({
    required this.polygon,
    this.building,
    this.amenity,
    this.name,
  });

  factory OsmFeature.fromJson(Map<String, dynamic> json) {
    final raw = json['polygon'] as List<dynamic>? ?? const [];
    final poly = raw
        .map((p) =>
            (p as List<dynamic>).map((c) => (c as num).toDouble()).toList())
        .toList();
    return OsmFeature(
      polygon: poly,
      building: json['building'] as String?,
      amenity: json['amenity'] as String?,
      name: json['name'] as String?,
    );
  }

  bool get isParking =>
      amenity == 'parking' || building == 'parking';
}

/// Raw OSM reference layer baked into the topology asset at publish. Used by
/// the on-device mini-map; never sent to the model.
class OsmLayer {
  final List<OsmFeature> features;
  final List<List<List<double>>> footways;

  const OsmLayer({this.features = const [], this.footways = const []});

  factory OsmLayer.fromJson(Map<String, dynamic> json) {
    final feats = (json['features'] as List<dynamic>? ?? [])
        .map((f) => OsmFeature.fromJson(f as Map<String, dynamic>))
        .toList();
    final ways = (json['footways'] as List<dynamic>? ?? [])
        .map<List<List<double>>>((w) => (w as List<dynamic>)
            .map((p) => (p as List<dynamic>)
                .map((c) => (c as num).toDouble())
                .toList())
            .toList())
        .toList();
    return OsmLayer(features: feats, footways: ways);
  }

  bool get isEmpty => features.isEmpty && footways.isEmpty;
}

class CampusGraph {
  final String facilityId;
  final String version;
  final Map<String, TopologyNode> nodes;
  final Map<String, List<TopologyEdge>> adjacency;
  final OsmLayer osm;

  const CampusGraph({
    required this.facilityId,
    required this.version,
    required this.nodes,
    required this.adjacency,
    this.osm = const OsmLayer(),
  });

  TopologyNode? nodeById(String id) => nodes[id];

  factory CampusGraph.fromJson(Map<String, dynamic> json) {
    final nodes = <String, TopologyNode>{};
    for (final n in (json['nodes'] as List<dynamic>? ?? [])) {
      final node = TopologyNode.fromJson(n as Map<String, dynamic>);
      nodes[node.id] = node;
    }

    final adjacency = <String, List<TopologyEdge>>{};
    for (final e in (json['edges'] as List<dynamic>? ?? [])) {
      final edge = TopologyEdge.fromJson(e as Map<String, dynamic>);
      (adjacency[edge.from] ??= []).add(edge);
    }

    final osmRaw = json['osm'] as Map<String, dynamic>?;
    final osm = osmRaw != null ? OsmLayer.fromJson(osmRaw) : const OsmLayer();

    return CampusGraph(
      facilityId: (json['facility_id'] as String?) ?? '',
      version: (json['version'] as String?) ?? '',
      nodes: nodes,
      adjacency: adjacency,
      osm: osm,
    );
  }
}

class RouteStep {
  final TopologyNode from;
  final TopologyNode to;
  final String instruction;
  final double distanceMeters;
  /// Pulled through from the underlying [TopologyEdge.accessibilityFeatures]
  /// at route construction time. Authoring source of truth for badges; the
  /// orchestrator reflects these into the model context so emitted JSON
  /// matches the structured data instead of relying on instruction parsing.
  final List<String> accessibilityFeatures;

  const RouteStep({
    required this.from,
    required this.to,
    required this.instruction,
    required this.distanceMeters,
    this.accessibilityFeatures = const [],
  });
}

/// Haversine distance between two lat/lng points in meters.
/// Used by `nearestNode` and any GPS-snapping work.
double haversineMeters(double lat1, double lng1, double lat2, double lng2) {
  const earthRadiusM = 6371000.0;
  final dLat = (lat2 - lat1) * math.pi / 180;
  final dLng = (lng2 - lng1) * math.pi / 180;
  final a = math.sin(dLat / 2) * math.sin(dLat / 2) +
      math.cos(lat1 * math.pi / 180) *
          math.cos(lat2 * math.pi / 180) *
          math.sin(dLng / 2) *
          math.sin(dLng / 2);
  final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
  return earthRadiusM * c;
}
