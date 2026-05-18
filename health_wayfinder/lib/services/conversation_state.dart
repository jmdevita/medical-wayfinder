import '../models/facility.dart';
import '../models/lookup_result.dart';
import '../models/topology.dart';
import 'wayfinding_tools.dart';

class ConversationState {
  Department? currentDepartment;
  /// Re-orientation anchor: where the user just said they are
  /// ("I'm near the elevators"). Ephemeral — cleared on new destination,
  /// because once the user picks a new place to go, their last "I'm at X"
  /// claim is presumed stale.
  TopologyNode? currentLocation;
  /// Session-wide starting point declared at the start of the visit
  /// (GPS fix or chip picker on first query, or photo flow later).
  /// Sticky — survives department changes and disambiguation, so routes
  /// always originate from where the patient actually entered the campus
  /// until they explicitly hit Start Over.
  TopologyNode? sessionOrigin;
  bool needsAccessibility;

  ConversationState({this.needsAccessibility = false});

  /// Returns true if the query mentions a department/alias that differs
  /// from the current one -- meaning we need a fresh lookup.
  /// Returns false for follow-up questions ("how far?", "I'm lost", etc.)
  bool shouldRelookup(String query, WayfindingTools tools) {
    // First turn always needs a lookup
    if (currentDepartment == null) return true;

    return tools.mentionsNewDepartment(query, currentDepartment);
  }

  void updateFromLookup(LookupResult result) {
    switch (result) {
      case LookupFound(:final department):
        if (currentDepartment?.name != department.name) {
          // New destination — drop any stale re-orientation anchor.
          currentLocation = null;
        }
        currentDepartment = department;
      case LookupAmbiguous():
        // Don't update current department until user selects
        break;
      case LookupNotFound():
        break;
    }
  }

  void selectFromDisambig(Department dept) {
    if (currentDepartment?.name != dept.name) {
      currentLocation = null;
    }
    currentDepartment = dept;
  }

  void reset() {
    currentDepartment = null;
    currentLocation = null;
    sessionOrigin = null;
  }
}
