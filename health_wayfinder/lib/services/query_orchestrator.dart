import '../models/facility.dart';
import '../models/lookup_result.dart';
import '../models/topology.dart';
import 'conversation_state.dart';
import 'wayfinding_tools.dart';

sealed class OrchestratorResult {
  const OrchestratorResult();
}

class Resolved extends OrchestratorResult {
  final Department department;
  final String directions;
  final AccessibilityInfo accessibility;
  final CheckInInfo checkIn;
  final List<RouteStep> route;

  const Resolved({
    required this.department,
    required this.directions,
    required this.accessibility,
    required this.checkIn,
    this.route = const [],
  });
}

class Disambig extends OrchestratorResult {
  final List<Department> candidates;
  const Disambig(this.candidates);
}

class ReOrientation extends OrchestratorResult {
  final TopologyNode currentLocation;
  final Department destination;
  final List<RouteStep> route;
  final String contextBlock;

  const ReOrientation({
    required this.currentLocation,
    required this.destination,
    required this.route,
    required this.contextBlock,
  });
}

class NeedsModel extends OrchestratorResult {
  final String query;
  final String contextBlock;
  const NeedsModel({required this.query, required this.contextBlock});
}

class QueryOrchestrator {
  final WayfindingTools tools;
  final ConversationState state;

  QueryOrchestrator({required this.tools}) : state = ConversationState();

  /// Process a user query through the deterministic orchestration pipeline.
  ///
  /// Returns:
  ///   - [Resolved]: a NEW destination has been determined; UI should
  ///     show a destination card. Only emitted when the lookup actually
  ///     resolves a department from the query — not for follow-ups
  ///     about the existing destination.
  ///   - [Disambig]: lookup matched multiple departments.
  ///   - [ReOrientation]: query was a landmark cue while a destination
  ///     was already set; UI should show a re-routed step carousel.
  ///   - [NeedsModel]: orchestrator can't add new structured data —
  ///     either the query is a follow-up about the current destination
  ///     ("how far?", "I'm lost"), or no destination has been determined
  ///     yet and the lookup didn't find one. The model responds with
  ///     whatever context block is current.
  OrchestratorResult processQuery(String query) {
    final reorient = _tryReOrientation(query);
    if (reorient != null) return reorient;

    if (state.shouldRelookup(query, tools)) {
      final result = tools.lookupDepartment(query);
      state.updateFromLookup(result);

      switch (result) {
        case LookupFound(:final department):
          return _buildResolved(department);
        case LookupAmbiguous(:final candidates):
          return Disambig(candidates);
        case LookupNotFound():
          // Fall through — let the model handle the unrecognized query.
          break;
      }
    }

    // Follow-up, or unrecognized query without a current destination.
    // Either way, no new structured retrieval — defer to the model
    // (which receives the current dept's context, if any).
    return NeedsModel(
      query: query,
      contextBlock: buildContextBlock(),
    );
  }

  /// Handle a disambiguation selection.
  OrchestratorResult selectFromDisambig(Department dept) {
    state.selectFromDisambig(dept);
    return _buildResolved(dept);
  }

  ReOrientation? _tryReOrientation(String query) {
    final dept = state.currentDepartment;
    if (dept == null) return null;
    final graph = tools.facility.topology;
    if (graph == null) return null;

    // If the query also names a different department, defer to lookup.
    // Patient saying "where is the building 5 lab" wants a destination,
    // not to be re-oriented to Building 5.
    if (tools.mentionsNewDepartment(query, dept)) return null;

    final located = tools.locateByLandmark(query);
    if (located == null) return null;

    final destNode = tools.destinationNodeFor(dept);
    if (destNode == null) return null;

    final route = tools.findRoute(
      located.id,
      destNode.id,
      accessibility: state.needsAccessibility,
    );
    if (route.isEmpty) return null;

    state.currentLocation = located;
    final ctx = buildReOrientationContextBlock(located, dept, route);
    return ReOrientation(
      currentLocation: located,
      destination: dept,
      route: route,
      contextBlock: ctx,
    );
  }

  Resolved _buildResolved(Department dept) {
    final directions = tools.getDirections(dept);
    final route = _routeForDept(dept);
    final accessibility = _aggregateAccessibility(dept, directions, route);
    final checkIn = tools.getCheckInInfo(dept);

    return Resolved(
      department: dept,
      directions: directions,
      accessibility: accessibility,
      checkIn: checkIn,
      route: route,
    );
  }

  List<RouteStep> _routeForDept(Department dept) {
    final graph = tools.facility.topology;
    if (graph == null) return const [];
    final origin = tools.originNodeFor(
      destination: dept,
      located: state.currentLocation,
      sessionOrigin: state.sessionOrigin,
    );
    final dest = tools.destinationNodeFor(dept);
    if (origin == null || dest == null) return const [];
    return tools.findRoute(
      origin.id,
      dest.id,
      accessibility: state.needsAccessibility,
    );
  }

  AccessibilityInfo _aggregateAccessibility(
    Department dept,
    String directions,
    List<RouteStep> route,
  ) {
    final base = tools.getAccessibility(dept, directions);
    if (route.isEmpty) return base;

    final features = {...base.features};
    for (final step in route) {
      // Prefer the structured per-edge tags (authored in Atlas). Fall back
      // to instruction-text scanning so legacy facilities without tags
      // still surface badges.
      if (step.accessibilityFeatures.isNotEmpty) {
        for (final f in step.accessibilityFeatures) {
          if (f != 'stairs') features.add(f);
        }
        continue;
      }
      final lower = step.instruction.toLowerCase();
      if (lower.contains('elevator')) features.add('elevator');
      if (lower.contains('ramp')) features.add('ramp');
      if (lower.contains('automatic') && lower.contains('door')) {
        features.add('automatic_doors');
      }
    }
    return AccessibilityInfo(
      accessible: base.accessible,
      features: features.toList(),
    );
  }

  /// Build a compact context block for the NeedsModel path (follow-ups
  /// or unrecognized queries). The prior resolved destination — if any —
  /// is included as historical context so the model can answer follow-ups
  /// about it ("how far?", "I'm lost"), but is labeled "Last resolved"
  /// so the model knows it may be stale and the patient may have moved on.
  String buildContextBlock() {
    final buf = StringBuffer();
    buf.writeln('Facility: ${tools.facility.name}');
    final phone = tools.facility.mainPhone;
    if (phone != null && phone.isNotEmpty) {
      buf.writeln('Main phone: $phone');
    }

    // Ground the model in the actual department list. Without this, when
    // the deterministic alias lookup misses (incomplete aliases, typos,
    // STT errors), the model has nothing to anchor to and either refuses
    // or hallucinates a department. With it, the model can do semantic
    // matching as a fallback to the regex alias index.
    final depts = tools.facility.departments;
    if (depts.isNotEmpty) {
      buf.writeln('Available departments:');
      for (final d in depts) {
        final aliasNote =
            d.aliases.isEmpty ? '' : ' (also: ${d.aliases.join(", ")})';
        buf.writeln('  - ${d.name}$aliasNote');
      }
    }

    final dept = state.currentDepartment;
    if (dept != null) {
      buf.writeln('Last resolved destination: ${dept.name}');
      buf.writeln('  Building: ${dept.building}');
      if (dept.floor.trim().isNotEmpty) buf.writeln('  Floor: ${dept.floor}');
      if (dept.hours != null) buf.writeln('  Hours: ${dept.hours}');
      if (dept.checkIn != null) buf.writeln('  Check-in: ${dept.checkIn}');
      buf.writeln('  Accessible: ${dept.accessible ? "Yes" : "No"}');

      final route = _routeForDept(dept);
      if (route.isNotEmpty) {
        final originLabel = route.first.from.label;
        buf.writeln('  Route from $originLabel:');
        if (state.needsAccessibility) {
          buf.writeln('  Accessibility mode: wheelchair (stair edges excluded)');
        }
        for (var i = 0; i < route.length; i++) {
          final step = route[i];
          final tags = step.accessibilityFeatures
              .where((f) => f != 'stairs')
              .toList();
          final tagNote = tags.isEmpty ? '' : ' [${tags.join(", ")}]';
          buf.writeln('    ${i + 1}. ${step.instruction}$tagNote');
        }
      } else {
        final directions = tools.getDirections(dept);
        if (directions.isNotEmpty) {
          buf.writeln('  Directions: $directions');
        }
      }

      final directionsForAccess = tools.getDirections(dept);
      final accessInfo = _aggregateAccessibility(dept, directionsForAccess, route);
      if (accessInfo.features.isNotEmpty) {
        buf.writeln('  Accessibility features: ${accessInfo.features.join(", ")}');
      }
    }

    return buf.toString().trimRight();
  }

  /// Build a context block for a re-orientation case: include current
  /// location and a recomputed route to the standing destination.
  String buildReOrientationContextBlock(
    TopologyNode located,
    Department dept,
    List<RouteStep> route,
  ) {
    final buf = StringBuffer();
    buf.writeln('Facility: ${tools.facility.name}');
    buf.writeln('Department: ${dept.name} (${dept.building})');
    buf.writeln('Current location: ${located.label}');
    buf.writeln('Route to destination:');
    if (state.needsAccessibility) {
      buf.writeln('Accessibility mode: wheelchair (stair edges excluded)');
    }
    for (var i = 0; i < route.length; i++) {
      final step = route[i];
      final tags = step.accessibilityFeatures
          .where((f) => f != 'stairs')
          .toList();
      final tagNote = tags.isEmpty ? '' : ' [${tags.join(", ")}]';
      buf.writeln('  ${i + 1}. ${step.instruction}$tagNote');
    }
    if (dept.checkIn != null) buf.writeln('Check-in: ${dept.checkIn}');
    return buf.toString().trimRight();
  }

  /// Build a context block for a disambiguation case.
  String buildDisambigContextBlock(List<Department> candidates) {
    final buf = StringBuffer();
    buf.writeln('Facility: ${tools.facility.name}');
    buf.writeln('Candidates:');
    for (final dept in candidates) {
      final parts = [dept.name, dept.building, if (dept.floor.trim().isNotEmpty) dept.floor];
      buf.writeln('- ${parts.join(', ')}');
    }
    return buf.toString().trimRight();
  }
}
