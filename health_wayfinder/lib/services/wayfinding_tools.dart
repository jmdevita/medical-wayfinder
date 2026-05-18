import '../models/facility.dart';
import '../models/lookup_result.dart';
import '../models/topology.dart';

class AccessibilityInfo {
  final bool accessible;
  final List<String> features;

  const AccessibilityInfo({
    required this.accessible,
    this.features = const [],
  });
}

class CheckInInfo {
  final String? checkIn;
  final String? hours;

  const CheckInInfo({this.checkIn, this.hours});
}

class WayfindingTools {
  final Facility facility;
  final Map<String, List<Department>> _aliasIndex;
  Map<String, List<TopologyNode>>? _keywordIndex;

  /// Word-boundary pattern: matches the alias only when it appears as a
  /// whole word (or multi-word phrase) in the query, not as a substring
  /// inside a longer word. E.g. "lab" matches "the lab" but not "laboratorio".
  ///
  /// Capped at [_maxCacheSize] entries with FIFO eviction so authoring
  /// sessions (which load many facilities into one process) don't grow
  /// the static cache unboundedly with patterns from facilities that are
  /// no longer in scope.
  static const _maxCacheSize = 256;
  static final _wordBoundaryCache = <String, RegExp>{};

  WayfindingTools(this.facility)
      : _aliasIndex = _buildAliasIndex(facility);

  static Map<String, List<Department>> _buildAliasIndex(Facility facility) {
    final index = <String, List<Department>>{};
    for (final dept in facility.departments) {
      for (final alias in dept.aliases) {
        final key = alias.toLowerCase();
        (index[key] ??= []).add(dept);
      }
      // Also index by department name
      final nameKey = dept.name.toLowerCase();
      (index[nameKey] ??= []).add(dept);
    }
    return index;
  }

  /// Check if [alias] appears as a whole-word match in [query].
  /// Tolerates an optional trailing 's' so "lab" matches "labs",
  /// "doctor" matches "doctors", etc. Does not match inside longer words
  /// (e.g. "lab" still doesn't match "laboratory" or "labrador").
  static bool _matchesWordBoundary(String query, String alias) {
    final cached = _wordBoundaryCache[alias];
    if (cached != null) return cached.hasMatch(query);
    if (_wordBoundaryCache.length >= _maxCacheSize) {
      // FIFO eviction: drop the oldest insertion.
      _wordBoundaryCache.remove(_wordBoundaryCache.keys.first);
    }
    final pattern = RegExp(
      '(?:^|\\s|[,;.!?])${RegExp.escape(alias)}s?(?:\$|\\s|[,;.!?])',
    );
    _wordBoundaryCache[alias] = pattern;
    return pattern.hasMatch(query);
  }

  /// Look up a department by a patient's natural-language query.
  /// Uses word-boundary matching and ranks by specificity (longer alias
  /// matches win over shorter ones) to avoid false positives.
  LookupResult lookupDepartment(String query) {
    final q = query.toLowerCase();

    // Collect all matches with their alias length (specificity score)
    final scored = <Department, int>{};
    for (final entry in _aliasIndex.entries) {
      if (_matchesWordBoundary(q, entry.key)) {
        for (final dept in entry.value) {
          final existing = scored[dept] ?? 0;
          if (entry.key.length > existing) {
            scored[dept] = entry.key.length;
          }
        }
      }
    }

    if (scored.isEmpty) {
      return const LookupNotFound();
    }

    // Sort by specificity (longest matching alias first)
    final sorted = scored.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    // If the top match is clearly more specific than the rest, resolve directly
    if (sorted.length == 1) {
      return LookupFound(sorted.first.key);
    }

    // If multiple matches have the same top score, disambiguate
    final topScore = sorted.first.value;
    final topMatches = sorted.where((e) => e.value == topScore).toList();

    if (topMatches.length == 1) {
      return LookupFound(topMatches.first.key);
    }

    return LookupAmbiguous(topMatches.map((e) => e.key).toList());
  }

  /// Get directions to a department, optionally from a specific parking area.
  /// If no parking is specified, auto-selects based on building proximity.
  String getDirections(Department dept, {String? fromParking}) {
    final dirMap = dept.directionsMap;
    if (dirMap.isEmpty) return '';

    // Single entry (JP-style "default" or single parking origin)
    if (dirMap.length == 1) return dirMap.values.first;

    // If caller specified a parking origin, try to match it
    if (fromParking != null) {
      final parkingKey = fromParking.toLowerCase();
      for (final entry in dirMap.entries) {
        if (entry.key.contains(parkingKey) ||
            parkingKey.contains(entry.key.replaceAll('from_', ''))) {
          return entry.value;
        }
      }
    }

    // Auto-select: find which parking area serves this building
    for (final area in facility.parking) {
      if (area.nearestBuildings.contains(dept.building)) {
        final areaKey = area.name.toLowerCase();
        for (final entry in dirMap.entries) {
          final dirKey = entry.key.replaceAll('from_', '').toLowerCase();
          if (areaKey.contains(dirKey)) {
            return entry.value;
          }
        }
      }
    }

    // Fallback: return first available
    return dirMap.values.first;
  }

  /// Get route-specific accessibility info by scanning the directions text.
  AccessibilityInfo getAccessibility(Department dept, String directions) {
    final features = <String>[];
    final lower = directions.toLowerCase();

    if (lower.contains('elevator')) features.add('elevator');
    if (lower.contains('ramp')) features.add('ramp');
    // Permissive "automatic doors" check — handles "automatic doors",
    // "automatic glass doors", "automatic sliding doors", etc.
    if (lower.contains('automatic') && lower.contains('door')) {
      features.add('automatic_doors');
    }
    if (lower.contains('accessible entrance') ||
        lower.contains('accessible,') ||
        lower.contains('(accessible')) {
      features.add('accessible_entrance');
    }

    return AccessibilityInfo(
      accessible: dept.accessible,
      features: features,
    );
  }

  /// Get check-in and hours info for a department.
  CheckInInfo getCheckInInfo(Department dept) {
    return CheckInInfo(checkIn: dept.checkIn, hours: dept.hours);
  }

  /// Check whether a query mentions any department alias that differs
  /// from the given current department. Used by ConversationState to
  /// decide whether to re-lookup or carry forward.
  bool mentionsNewDepartment(String query, Department? current) {
    final q = query.toLowerCase();
    for (final entry in _aliasIndex.entries) {
      if (_matchesWordBoundary(q, entry.key)) {
        for (final dept in entry.value) {
          if (current == null || dept.name != current.name) {
            return true;
          }
        }
      }
    }
    return false;
  }

  // --- Topology routing ----------------------------------------------------

  /// Match a patient's free-text description to the best topology node by
  /// keyword. Specificity wins (longer keyword first); ties are broken by
  /// node-type priority so e.g. an entrance node beats a generic landmark.
  /// Returns null when nothing matches or topology is missing.
  TopologyNode? locateByLandmark(String description) {
    final graph = facility.topology;
    if (graph == null) return null;

    final index = _keywordIndex ??= _buildKeywordIndex(graph);
    final q = description.toLowerCase();
    final scored = <TopologyNode, int>{};
    for (final entry in index.entries) {
      if (_matchesWordBoundary(q, entry.key)) {
        for (final node in entry.value) {
          final existing = scored[node] ?? 0;
          if (entry.key.length > existing) {
            scored[node] = entry.key.length;
          }
        }
      }
    }
    if (scored.isEmpty) return null;

    final sorted = scored.entries.toList()
      ..sort((a, b) {
        final byScore = b.value.compareTo(a.value);
        if (byScore != 0) return byScore;
        return _nodeTypePriority(a.key.type)
            .compareTo(_nodeTypePriority(b.key.type));
      });
    return sorted.first.key;
  }

  static int _nodeTypePriority(NodeType t) {
    switch (t) {
      case NodeType.entrance:
        return 0;
      case NodeType.parking:
        return 1;
      case NodeType.landmark:
        return 2;
      case NodeType.transit:
        return 3;
      case NodeType.junction:
        return 4;
      case NodeType.floor:
        return 5;
    }
  }

  /// Find the shortest path between two nodes via Dijkstra. Edges are
  /// treated as bidirectional (patients can walk back the way they came);
  /// when an edge is used in reverse, a "Head back toward …" instruction
  /// is synthesized so each step still reads naturally. Returns an empty
  /// list when topology is missing or no path exists. Skips `blocked`.
  ///
  /// When [accessibility] is true, edges tagged `stairs` in
  /// [TopologyEdge.accessibilityFeatures] are excluded so wheelchair users
  /// route through elevators/ramps instead.
  List<RouteStep> findRoute(
    String fromNodeId,
    String toNodeId, {
    bool accessibility = false,
  }) {
    final graph = facility.topology;
    if (graph == null) return const [];
    if (graph.nodeById(fromNodeId) == null ||
        graph.nodeById(toNodeId) == null) {
      return const [];
    }
    if (fromNodeId == toNodeId) return const [];

    // Build undirected adjacency: each directed edge becomes an outgoing
    // option for both endpoints, tagged with whether traversal is reversed.
    final undirected = <String, List<_DirEdge>>{};
    for (final outgoing in graph.adjacency.values) {
      for (final edge in outgoing) {
        if (edge.blocked) continue;
        if (accessibility && edge.requiresStairs) continue;
        (undirected[edge.from] ??= []).add(_DirEdge(edge, reversed: false));
        (undirected[edge.to] ??= []).add(_DirEdge(edge, reversed: true));
      }
    }

    final dist = <String, double>{fromNodeId: 0};
    final prev = <String, _DirEdge>{};
    final visited = <String>{};
    final queue = HeapPriorityQueue<_PqEntry>();
    queue.add(_PqEntry(fromNodeId, 0));

    while (queue.isNotEmpty) {
      final cur = queue.removeFirst();
      if (!visited.add(cur.id)) continue;
      if (cur.id == toNodeId) break;

      for (final dir in undirected[cur.id] ?? const <_DirEdge>[]) {
        final nextId = dir.reversed ? dir.edge.from : dir.edge.to;
        final candidate = cur.dist + dir.edge.cost;
        final best = dist[nextId];
        if (best == null || candidate < best) {
          dist[nextId] = candidate;
          prev[nextId] = dir;
          queue.add(_PqEntry(nextId, candidate));
        }
      }
    }

    if (!prev.containsKey(toNodeId)) return const [];

    final reversed = <_DirEdge>[];
    var cursor = toNodeId;
    while (cursor != fromNodeId) {
      final dir = prev[cursor];
      if (dir == null) return const [];
      reversed.add(dir);
      cursor = dir.reversed ? dir.edge.to : dir.edge.from;
    }

    return reversed.reversed.map((dir) {
      final edge = dir.edge;
      final fromId = dir.reversed ? edge.to : edge.from;
      final toId = dir.reversed ? edge.from : edge.to;
      final fromNode = graph.nodeById(fromId)!;
      final toNode = graph.nodeById(toId)!;
      final instruction = dir.reversed
          ? 'Head back toward ${toNode.label}.'
          : edge.instruction;
      return RouteStep(
        from: fromNode,
        to: toNode,
        instruction: instruction,
        distanceMeters: edge.distanceMeters,
        accessibilityFeatures: edge.accessibilityFeatures,
      );
    }).toList();
  }

  /// Nearest topology node to a GPS point. Skips nodes without lat/lng.
  TopologyNode? nearestNode(double lat, double lng) {
    final graph = facility.topology;
    if (graph == null) return null;
    TopologyNode? best;
    double bestMeters = double.infinity;
    for (final node in graph.nodes.values) {
      if (node.lat == null || node.lng == null) continue;
      final d = haversineMeters(lat, lng, node.lat!, node.lng!);
      if (d < bestMeters) {
        bestMeters = d;
        best = node;
      }
    }
    return best;
  }

  /// Resolve the destination node for a department.
  /// Prefers an explicit `topology_node_id` on the department record so
  /// that distinct departments in the same building (e.g. ER vs Radiology
  /// both in "Hospital") route to different entrances. Falls back to
  /// matching `dept.building` against entrance-type node labels.
  TopologyNode? destinationNodeFor(Department dept) {
    final graph = facility.topology;
    if (graph == null) return null;

    final explicit = dept.topologyNodeId;
    if (explicit != null) {
      final node = graph.nodeById(explicit);
      if (node != null) return node;
    }

    final wanted = dept.building.toLowerCase();
    for (final node in graph.nodes.values) {
      if (node.type == NodeType.entrance &&
          node.label.toLowerCase() == wanted) {
        return node;
      }
    }
    // Fallback: substring match (handles "Building 3" vs "Building 3 entrance").
    for (final node in graph.nodes.values) {
      if (node.type == NodeType.entrance &&
          node.label.toLowerCase().contains(wanted)) {
        return node;
      }
    }
    return null;
  }

  /// Resolve the origin node for routing.
  ///
  /// Priority:
  ///   1. [located] — re-orientation anchor ("I'm near the elevators").
  ///      Highest because it's the user's most recent explicit claim.
  ///   2. [sessionOrigin] — where the user declared they were starting from
  ///      (GPS / picker / photo) at the start of the visit. Sticky across
  ///      department changes.
  ///   3. Parking heuristic — the parking node tagged as serving the
  ///      destination's building.
  ///   4. Any parking node, as a last resort.
  TopologyNode? originNodeFor({
    Department? destination,
    TopologyNode? located,
    TopologyNode? sessionOrigin,
  }) {
    final graph = facility.topology;
    if (graph == null) return null;
    if (located != null) return located;
    if (sessionOrigin != null) return sessionOrigin;

    if (destination != null) {
      for (final area in facility.parking) {
        if (!area.nearestBuildings.contains(destination.building)) continue;
        final areaLower = area.name.toLowerCase();
        for (final node in graph.nodes.values) {
          if (node.type != NodeType.parking) continue;
          if (areaLower.contains(node.label.toLowerCase()) ||
              node.label.toLowerCase().contains(areaLower.split(' ').first)) {
            return node;
          }
        }
      }
    }

    for (final node in graph.nodes.values) {
      if (node.type == NodeType.parking) return node;
    }
    return null;
  }

  static Map<String, List<TopologyNode>> _buildKeywordIndex(CampusGraph graph) {
    final index = <String, List<TopologyNode>>{};
    for (final node in graph.nodes.values) {
      for (final kw in node.keywords) {
        final key = kw.toLowerCase();
        (index[key] ??= []).add(node);
      }
      // Also index by label for direct matches like "Building 5".
      final labelKey = node.label.toLowerCase();
      (index[labelKey] ??= []).add(node);
    }
    return index;
  }
}

class _PqEntry implements Comparable<_PqEntry> {
  final String id;
  final double dist;
  const _PqEntry(this.id, this.dist);

  @override
  int compareTo(_PqEntry other) => dist.compareTo(other.dist);
}

class _DirEdge {
  final TopologyEdge edge;
  final bool reversed;
  const _DirEdge(this.edge, {required this.reversed});
}

/// Minimal binary-heap priority queue. Avoids pulling in `package:collection`.
class HeapPriorityQueue<E extends Comparable<E>> {
  final List<E> _heap = [];

  bool get isNotEmpty => _heap.isNotEmpty;
  int get length => _heap.length;

  void add(E value) {
    _heap.add(value);
    _siftUp(_heap.length - 1);
  }

  E removeFirst() {
    final result = _heap.first;
    final last = _heap.removeLast();
    if (_heap.isNotEmpty) {
      _heap[0] = last;
      _siftDown(0);
    }
    return result;
  }

  void _siftUp(int i) {
    while (i > 0) {
      final parent = (i - 1) >> 1;
      if (_heap[i].compareTo(_heap[parent]) >= 0) break;
      _swap(i, parent);
      i = parent;
    }
  }

  void _siftDown(int i) {
    final n = _heap.length;
    while (true) {
      final l = 2 * i + 1;
      final r = 2 * i + 2;
      var smallest = i;
      if (l < n && _heap[l].compareTo(_heap[smallest]) < 0) smallest = l;
      if (r < n && _heap[r].compareTo(_heap[smallest]) < 0) smallest = r;
      if (smallest == i) break;
      _swap(i, smallest);
      i = smallest;
    }
  }

  void _swap(int a, int b) {
    final tmp = _heap[a];
    _heap[a] = _heap[b];
    _heap[b] = tmp;
  }
}
