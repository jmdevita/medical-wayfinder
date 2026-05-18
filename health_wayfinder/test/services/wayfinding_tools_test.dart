import 'package:flutter_test/flutter_test.dart';
import 'package:health_wayfinder/models/facility.dart';
import 'package:health_wayfinder/models/lookup_result.dart';
import 'package:health_wayfinder/models/topology.dart';
import 'package:health_wayfinder/services/wayfinding_tools.dart';
import 'package:health_wayfinder/services/conversation_state.dart';
import 'package:health_wayfinder/services/query_orchestrator.dart';

// --- Test fixtures ---

final _kaiserFacility = Facility(
  id: 'kaiser_panorama_city',
  name: 'Kaiser Permanente Panorama City',
  address: '13652 Cantara St',
  type: 'Hospital',
  parking: [
    ParkingArea(
      name: 'Cantara Street Parking',
      nearestBuildings: ['Building 2', 'Building 3', 'Building 4'],
      entranceNote: 'Exit toward campus.',
    ),
    ParkingArea(
      name: 'Ventura Canyon Parking',
      nearestBuildings: ['Building 5', 'Building 6', 'Hospital'],
      entranceNote: 'Exit toward Roscoe.',
    ),
  ],
  departments: [
    Department(
      name: 'Lab / Blood Draw (Building 3)',
      building: 'Building 3',
      floor: 'Basement (Area 060)',
      hours: 'Mon-Fri, 7:00 AM - 5:15 PM',
      accessible: true,
      aliases: ['blood place', 'blood test', 'lab', 'laboratory', 'laboratorio'],
      checkIn: 'Check in at the lab window',
      directionsMap: {
        'from_cantara': 'Exit Cantara St parking. Building 3 straight ahead. Enter through automatic doors. Take elevator to basement.',
      },
    ),
    Department(
      name: 'Pharmacy (Cantara / Building 3)',
      building: 'Building 3',
      floor: 'Ground floor',
      accessible: true,
      aliases: ['pharmacy', 'farmacia', 'prescriptions'],
      checkIn: 'Drop off at pharmacy window',
      directionsMap: {
        'from_cantara': 'Exit Cantara parking. Building 3 straight ahead. Pharmacy is on the ground floor.',
      },
    ),
    Department(
      name: 'Pharmacy (Ventura Canyon / Building 6)',
      building: 'Building 6',
      floor: 'Ground floor',
      accessible: true,
      aliases: ['pharmacy', 'farmacia', 'prescriptions'],
      checkIn: 'Drop off at pharmacy window',
      directionsMap: {
        'from_ventura': 'Exit Ventura Canyon parking. Building 6 is ahead. Pharmacy on ground floor.',
      },
    ),
    Department(
      name: 'Pediatrics',
      building: 'Building 2',
      floor: '1st floor',
      accessible: true,
      aliases: ['kids doctor', 'pediatrics', 'pediatria', 'my kid'],
      checkIn: 'Check in at Pediatrics front desk',
      directionsMap: {
        'from_cantara': 'Exit Cantara parking. Building 2 is to your left. Enter through accessible ramp entrance.',
      },
    ),
    Department(
      name: 'Emergency Department',
      building: 'Hospital',
      floor: 'Ground floor',
      accessible: true,
      aliases: ['er', 'emergency', 'emergencia', 'sala de emergencias'],
      checkIn: 'Check in at triage desk',
      directionsMap: {
        'from_ventura': 'Exit Ventura Canyon parking. Emergency has separate entrance with red signage.',
      },
    ),
    Department(
      name: 'Allergy',
      building: 'Building 5',
      floor: '2nd floor',
      accessible: true,
      aliases: ['allergy', 'allergist', 'alergia'],
      checkIn: 'Check in at Allergy reception',
      directionsMap: {
        'from_ventura': 'Exit Ventura Canyon parking. Building 5 is to your left.',
      },
    ),
  ],
);

final _jpFacility = Facility(
  id: 'southern_jp',
  name: 'Southern Jamaica Plain Health Center',
  address: '640 Centre St',
  type: 'Community health center',
  parking: [
    ParkingArea(
      name: 'Under-building parking',
      nearestBuildings: ['Main building'],
      entranceNote: 'From Centre St entrance.',
    ),
  ],
  departments: [
    Department(
      name: 'Adult Medicine',
      building: 'Main building',
      floor: '1st floor',
      accessible: true,
      aliases: ['regular doctor', 'primary care', 'mi doctor'],
      checkIn: 'Check in at the front desk',
      directionsMap: {
        'default': 'Enter through main entrance (automatic doors). Check in at front desk.',
      },
    ),
  ],
);

void main() {
  // -------------------------------------------------------
  // WayfindingTools.lookupDepartment
  // -------------------------------------------------------

  group('lookupDepartment', () {
    late WayfindingTools tools;

    setUp(() {
      tools = WayfindingTools(_kaiserFacility);
    });

    test('finds single match by alias', () {
      final result = tools.lookupDepartment('where is the blood place');
      expect(result, isA<LookupFound>());
      expect((result as LookupFound).department.name, 'Lab / Blood Draw (Building 3)');
    });

    test('finds single match by Spanish alias', () {
      final result = tools.lookupDepartment('donde esta el laboratorio');
      expect(result, isA<LookupFound>());
      expect((result as LookupFound).department.name, 'Lab / Blood Draw (Building 3)');
    });

    test('returns ambiguous for pharmacy (2 locations)', () {
      final result = tools.lookupDepartment('I need the pharmacy');
      expect(result, isA<LookupAmbiguous>());
      final candidates = (result as LookupAmbiguous).candidates;
      expect(candidates.length, 2);
      expect(candidates.map((d) => d.name), containsAll([
        'Pharmacy (Cantara / Building 3)',
        'Pharmacy (Ventura Canyon / Building 6)',
      ]));
    });

    test('returns not found for unknown query', () {
      final result = tools.lookupDepartment('where is the swimming pool');
      expect(result, isA<LookupNotFound>());
    });

    test('matches department name directly', () {
      final result = tools.lookupDepartment('Pediatrics');
      expect(result, isA<LookupFound>());
      expect((result as LookupFound).department.name, 'Pediatrics');
    });

    test('does not false-positive on substring inside longer word', () {
      // "lab" should not match when it appears inside "laboratorio"
      // (laboratorio is a separate alias on the same dept here, but
      // the principle matters for cross-dept collisions)
      final result = tools.lookupDepartment('I have an elaborate plan');
      expect(result, isA<LookupNotFound>());
    });

    test('prefers longer alias match over shorter one', () {
      // "blood place" (longer, more specific) should win over "lab" (shorter)
      final result = tools.lookupDepartment('where is the blood place');
      expect(result, isA<LookupFound>());
      expect((result as LookupFound).department.name, 'Lab / Blood Draw (Building 3)');
    });

    test('handles query with only short common words', () {
      // "my kid" should match pediatrics alias
      final result = tools.lookupDepartment('my kid has an appointment');
      expect(result, isA<LookupFound>());
      expect((result as LookupFound).department.name, 'Pediatrics');
    });

    test('short alias "er" does not match inside "allergy"', () {
      // "er" is an alias for Emergency, but "allergy" contains "er" as substring
      // Word-boundary matching should prevent this false positive
      final result = tools.lookupDepartment('I have allergy issues');
      expect(result, isA<LookupFound>());
      expect((result as LookupFound).department.name, 'Allergy');
    });

    test('short alias "er" matches when standalone', () {
      final result = tools.lookupDepartment('take me to the er');
      expect(result, isA<LookupFound>());
      expect((result as LookupFound).department.name, 'Emergency Department');
    });

    test('matches plural forms ("labs" -> "lab", "doctors" -> "doctor")', () {
      // "lab" alias should match "labs" via the optional s-suffix in the
      // word-boundary regex.
      final r1 = tools.lookupDepartment('I need to get to the labs');
      expect(r1, isA<LookupFound>());
      expect((r1 as LookupFound).department.name,
          'Lab / Blood Draw (Building 3)');

      // Negative: "lab" still must not match inside "laboratory" — that's
      // handled by the existing same-dept aliasing, but verify the regex
      // doesn't drift to matching arbitrary substrings.
      final r2 = tools.lookupDepartment('I have an elaborate plan');
      expect(r2, isA<LookupNotFound>());
    });
  });

  // -------------------------------------------------------
  // WayfindingTools.getDirections
  // -------------------------------------------------------

  group('getDirections', () {
    test('returns parking-specific directions for Kaiser', () {
      final tools = WayfindingTools(_kaiserFacility);
      final lab = _kaiserFacility.departments[0];
      final directions = tools.getDirections(lab);
      expect(directions, contains('Cantara'));
      expect(directions, contains('elevator'));
    });

    test('returns generic directions for JP', () {
      final tools = WayfindingTools(_jpFacility);
      final dept = _jpFacility.departments[0];
      final directions = tools.getDirections(dept);
      expect(directions, contains('main entrance'));
    });

    test('auto-selects correct parking by building', () {
      final tools = WayfindingTools(_kaiserFacility);
      // Building 6 pharmacy should get ventura directions
      final pharmacy6 = _kaiserFacility.departments[2];
      final directions = tools.getDirections(pharmacy6);
      expect(directions, contains('Ventura'));
    });
  });

  // -------------------------------------------------------
  // WayfindingTools.getAccessibility
  // -------------------------------------------------------

  group('getAccessibility', () {
    test('detects elevator and automatic doors from directions', () {
      final tools = WayfindingTools(_kaiserFacility);
      final lab = _kaiserFacility.departments[0];
      final directions = tools.getDirections(lab);
      final info = tools.getAccessibility(lab, directions);
      expect(info.accessible, isTrue);
      expect(info.features, contains('elevator'));
      expect(info.features, contains('automatic_doors'));
    });

    test('detects ramp from directions', () {
      final tools = WayfindingTools(_kaiserFacility);
      final peds = _kaiserFacility.departments[3]; // Pediatrics with ramp
      final directions = tools.getDirections(peds);
      final info = tools.getAccessibility(peds, directions);
      expect(info.features, contains('ramp'));
    });
  });

  // -------------------------------------------------------
  // WayfindingTools.getCheckInInfo
  // -------------------------------------------------------

  group('getCheckInInfo', () {
    test('returns check-in and hours', () {
      final tools = WayfindingTools(_kaiserFacility);
      final lab = _kaiserFacility.departments[0];
      final info = tools.getCheckInInfo(lab);
      expect(info.checkIn, 'Check in at the lab window');
      expect(info.hours, 'Mon-Fri, 7:00 AM - 5:15 PM');
    });
  });

  // -------------------------------------------------------
  // WayfindingTools.mentionsNewDepartment
  // -------------------------------------------------------

  group('mentionsNewDepartment', () {
    test('returns true when query mentions a different department', () {
      final tools = WayfindingTools(_kaiserFacility);
      final lab = _kaiserFacility.departments[0];
      expect(tools.mentionsNewDepartment('where is the pharmacy', lab), isTrue);
    });

    test('returns false for follow-up questions', () {
      final tools = WayfindingTools(_kaiserFacility);
      final lab = _kaiserFacility.departments[0];
      expect(tools.mentionsNewDepartment('how far is it', lab), isFalse);
      expect(tools.mentionsNewDepartment("I'm lost", lab), isFalse);
    });

    test('returns false when query mentions same department', () {
      final tools = WayfindingTools(_kaiserFacility);
      final lab = _kaiserFacility.departments[0];
      expect(tools.mentionsNewDepartment('the lab again please', lab), isFalse);
    });
  });

  // -------------------------------------------------------
  // ConversationState
  // -------------------------------------------------------

  group('ConversationState', () {
    test('shouldRelookup returns true on first query', () {
      final tools = WayfindingTools(_kaiserFacility);
      final state = ConversationState();
      expect(state.shouldRelookup('where is the lab', tools), isTrue);
    });

    test('shouldRelookup returns false for follow-up', () {
      final tools = WayfindingTools(_kaiserFacility);
      final state = ConversationState();
      state.currentDepartment = _kaiserFacility.departments[0]; // lab
      expect(state.shouldRelookup('how far is it', tools), isFalse);
    });

    test('shouldRelookup returns true for new department', () {
      final tools = WayfindingTools(_kaiserFacility);
      final state = ConversationState();
      state.currentDepartment = _kaiserFacility.departments[0]; // lab
      expect(state.shouldRelookup('where is the pharmacy', tools), isTrue);
    });

    test('reset clears state', () {
      final state = ConversationState();
      state.currentDepartment = _kaiserFacility.departments[0];
      state.sessionOrigin = const TopologyNode(
        id: 'origin', type: NodeType.parking, label: 'Test lot',
        description: '',
      );
      state.reset();
      expect(state.currentDepartment, isNull);
      expect(state.sessionOrigin, isNull);
    });

    test('updateFromLookup clears currentLocation on dept change', () {
      final state = ConversationState();
      state.currentDepartment = _kaiserFacility.departments[0]; // lab
      state.currentLocation = const TopologyNode(
        id: 'glass', type: NodeType.entrance, label: 'Building 5',
        description: '',
      );
      // Same department — don't clear.
      state.updateFromLookup(LookupFound(_kaiserFacility.departments[0]));
      expect(state.currentLocation, isNotNull);
      // Different department — clear.
      state.updateFromLookup(LookupFound(_kaiserFacility.departments[3]));
      expect(state.currentLocation, isNull);
    });

    test('selectFromDisambig clears currentLocation on dept change', () {
      final state = ConversationState();
      state.currentDepartment = _kaiserFacility.departments[0];
      state.currentLocation = const TopologyNode(
        id: 'glass', type: NodeType.entrance, label: 'Building 5',
        description: '',
      );
      state.selectFromDisambig(_kaiserFacility.departments[3]);
      expect(state.currentLocation, isNull);
    });
  });

  // -------------------------------------------------------
  // QueryOrchestrator
  // -------------------------------------------------------

  group('QueryOrchestrator', () {
    test('resolves a clear department query', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      final result = orch.processQuery('where is the blood place');
      expect(result, isA<Resolved>());
      final resolved = result as Resolved;
      expect(resolved.department.name, 'Lab / Blood Draw (Building 3)');
      expect(resolved.directions, isNotEmpty);
      expect(resolved.checkIn.checkIn, 'Check in at the lab window');
    });

    test('returns disambig for ambiguous query', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      final result = orch.processQuery('I need the pharmacy');
      expect(result, isA<Disambig>());
      expect((result as Disambig).candidates.length, 2);
    });

    test('selectFromDisambig resolves to chosen department', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      orch.processQuery('I need the pharmacy'); // disambig
      final dept = _kaiserFacility.departments[1]; // Cantara pharmacy
      final result = orch.selectFromDisambig(dept);
      expect(result, isA<Resolved>());
      expect((result as Resolved).department.name, 'Pharmacy (Cantara / Building 3)');
    });

    test('follow-up returns NeedsModel with current dept in context', () {
      // The orchestrator only emits Resolved for NEW destinations. A
      // follow-up about the already-resolved dept ("how far?") should
      // route to the model so it can answer using the existing context,
      // NOT re-emit a duplicate destination card.
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      orch.processQuery('where is the blood place');
      final result = orch.processQuery('how far is it');
      expect(result, isA<NeedsModel>());
      expect((result as NeedsModel).contextBlock, contains('Lab'));
      // State preserves the current dept so context is populated.
      expect(orch.state.currentDepartment?.name,
          'Lab / Blood Draw (Building 3)');
    });

    test('re-lookup on new department mention', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      orch.processQuery('where is the blood place');
      final result = orch.processQuery('actually where is pediatrics');
      expect(result, isA<Resolved>());
      expect((result as Resolved).department.name, 'Pediatrics');
    });

    test('returns NeedsModel for unknown queries', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      final result = orch.processQuery('hello there');
      expect(result, isA<NeedsModel>());
    });

    test('buildContextBlock is compact', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      orch.processQuery('where is the blood place');
      final block = orch.buildContextBlock();
      expect(block, contains('Lab / Blood Draw'));
      expect(block, contains('Building 3'));
      // Should be well under 1000 chars
      expect(block.length, lessThan(1000));
    });

    test('buildDisambigContextBlock lists candidates', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      final candidates = _kaiserFacility.departments.where(
        (d) => d.name.contains('Pharmacy'),
      ).toList();
      final block = orch.buildDisambigContextBlock(candidates);
      expect(block, contains('Candidates:'));
      expect(block, contains('Pharmacy (Cantara'));
      expect(block, contains('Pharmacy (Ventura'));
    });

    test('state resets on reset', () {
      final orch = QueryOrchestrator(
        tools: WayfindingTools(_kaiserFacility),
      );
      orch.processQuery('where is the lab');
      expect(orch.state.currentDepartment, isNotNull);
      orch.state.reset();
      expect(orch.state.currentDepartment, isNull);
    });
  });

  // -------------------------------------------------------
  // Topology routing
  // -------------------------------------------------------

  group('Topology routing', () {
    Facility kaiserWithGraph() => Facility(
          id: _kaiserFacility.id,
          name: _kaiserFacility.name,
          address: _kaiserFacility.address,
          type: _kaiserFacility.type,
          parking: _kaiserFacility.parking,
          departments: _kaiserFacility.departments,
          topology: _buildTestGraph(),
        );

    test('locateByLandmark matches "glass building" to Building 5', () {
      final tools = WayfindingTools(kaiserWithGraph());
      final node = tools.locateByLandmark('I see the glass building');
      expect(node, isNotNull);
      expect(node!.id, 'building_5_entrance');
    });

    test('locateByLandmark returns null for non-landmark text', () {
      final tools = WayfindingTools(kaiserWithGraph());
      expect(tools.locateByLandmark('I have an appointment at 3pm'), isNull);
    });

    test('locateByLandmark returns null when topology missing', () {
      final tools = WayfindingTools(_kaiserFacility); // no topology
      expect(tools.locateByLandmark('glass building'), isNull);
    });

    test('findRoute returns single hop from cantara_parking to building_3', () {
      final tools = WayfindingTools(kaiserWithGraph());
      final route =
          tools.findRoute('cantara_parking', 'building_3_entrance');
      expect(route, isNotEmpty);
      expect(route.first.from.id, 'cantara_parking');
      expect(route.last.to.id, 'building_3_entrance');
    });

    test('findRoute traverses multi-hop path', () {
      final tools = WayfindingTools(kaiserWithGraph());
      final route =
          tools.findRoute('cantara_parking', 'building_5_entrance');
      expect(route.length, greaterThanOrEqualTo(2));
      expect(route.first.from.id, 'cantara_parking');
      expect(route.last.to.id, 'building_5_entrance');
    });

    test('findRoute routes around blocked edges', () {
      final graph = _buildTestGraph(blockBuildingThreeToFour: true);
      final tools = WayfindingTools(Facility(
        id: 'k',
        name: 'k',
        address: '',
        type: 'h',
        parking: _kaiserFacility.parking,
        departments: _kaiserFacility.departments,
        topology: graph,
      ));
      final route =
          tools.findRoute('building_3_entrance', 'building_4_entrance');
      // Should still find a path via the fountain detour.
      expect(route, isNotEmpty);
      final ids = route.map((s) => '${s.from.id}->${s.to.id}').toList();
      expect(ids.any((s) => s == 'building_3_entrance->building_4_entrance'),
          isFalse);
    });

    test('findRoute returns empty when topology missing', () {
      final tools = WayfindingTools(_kaiserFacility);
      expect(tools.findRoute('a', 'b'), isEmpty);
    });

    test('findRoute returns empty when nodes unknown', () {
      final tools = WayfindingTools(kaiserWithGraph());
      expect(tools.findRoute('does_not_exist', 'building_3_entrance'), isEmpty);
    });

    test('nearestNode picks closest by haversine', () {
      final tools = WayfindingTools(kaiserWithGraph());
      final node = tools.nearestNode(34.22878, -118.44520);
      expect(node, isNotNull);
      expect(node!.id, 'building_2_entrance');
    });

    test('destinationNodeFor matches building label', () {
      final tools = WayfindingTools(kaiserWithGraph());
      final lab = _kaiserFacility.departments[0];
      final node = tools.destinationNodeFor(lab);
      expect(node, isNotNull);
      expect(node!.id, 'building_3_entrance');
    });

    test('originNodeFor falls back to default parking when no parking set', () {
      final tools = WayfindingTools(kaiserWithGraph());
      final lab = _kaiserFacility.departments[0]; // Building 3
      final origin = tools.originNodeFor(destination: lab);
      expect(origin, isNotNull);
      expect(origin!.type, NodeType.parking);
    });

    test('destinationNodeFor honors explicit topology_node_id', () {
      // Construct a department with the same building as another, but
      // with an explicit node id pointing to a different entrance.
      const fakeDept = Department(
        name: 'Emergency',
        building: 'Building 3', // same as lab — would normally collide
        floor: 'Ground',
        topologyNodeId: 'building_5_entrance',
      );
      final tools = WayfindingTools(kaiserWithGraph());
      final node = tools.destinationNodeFor(fakeDept);
      expect(node, isNotNull);
      expect(node!.id, 'building_5_entrance');
    });

    test('locateByLandmark prefers entrance over landmark on tie', () {
      // Build a graph where two nodes share a same-length keyword.
      final graph = CampusGraph(
        facilityId: 'test',
        version: 't',
        nodes: {
          'glass_entrance': const TopologyNode(
            id: 'glass_entrance', type: NodeType.entrance,
            label: 'Glass building', description: '',
            keywords: ['glass'],
          ),
          'glass_marker': const TopologyNode(
            id: 'glass_marker', type: NodeType.landmark,
            label: 'Glass marker', description: '',
            keywords: ['glass'],
          ),
        },
        adjacency: const {},
      );
      final tools = WayfindingTools(Facility(
        id: 't', name: 't', address: '', type: 't', topology: graph,
      ));
      final node = tools.locateByLandmark('I see the glass over there');
      expect(node, isNotNull);
      expect(node!.id, 'glass_entrance');
    });
  });

  // -------------------------------------------------------
  // Orchestrator + topology integration
  // -------------------------------------------------------

  group('QueryOrchestrator with topology', () {
    Facility kaiserWithGraph() => Facility(
          id: _kaiserFacility.id,
          name: _kaiserFacility.name,
          address: _kaiserFacility.address,
          type: _kaiserFacility.type,
          parking: _kaiserFacility.parking,
          departments: _kaiserFacility.departments,
          topology: _buildTestGraph(),
        );

    test('Resolved includes route when topology present', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(kaiserWithGraph()));
      final result = orch.processQuery('where is the blood place');
      expect(result, isA<Resolved>());
      final resolved = result as Resolved;
      expect(resolved.route, isNotEmpty);
      expect(resolved.route.last.to.id, 'building_3_entrance');
    });

    test('Resolved without topology has empty route', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(_kaiserFacility));
      final result = orch.processQuery('where is the blood place');
      expect((result as Resolved).route, isEmpty);
    });

    test('re-orientation triggers after destination is set', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(kaiserWithGraph()));
      orch.processQuery('where is the blood place');
      final result = orch.processQuery('I see the glass building');
      expect(result, isA<ReOrientation>());
      final reorient = result as ReOrientation;
      expect(reorient.currentLocation.id, 'building_5_entrance');
      expect(reorient.destination.name, contains('Lab'));
      expect(reorient.route, isNotEmpty);
      expect(reorient.contextBlock, contains('Current location'));
    });

    test('re-orientation falls back to NeedsModel without topology', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(_kaiserFacility));
      orch.processQuery('where is the blood place');
      final result = orch.processQuery('I see the glass building');
      // No topology → not ReOrientation. Either Resolved (carry-forward) or
      // NeedsModel — both are acceptable; we just want NOT a ReOrientation.
      expect(result, isNot(isA<ReOrientation>()));
    });

    test('buildContextBlock includes Route line when topology present', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(kaiserWithGraph()));
      orch.processQuery('where is the blood place');
      final block = orch.buildContextBlock();
      expect(block, contains('Route from'));
      expect(block, contains('Building 3'));
    });

    test('buildContextBlock falls back to Directions without topology', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(_kaiserFacility));
      orch.processQuery('where is the blood place');
      final block = orch.buildContextBlock();
      expect(block, contains('Directions:'));
      expect(block, isNot(contains('Route from')));
    });

    test('reset clears currentLocation', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(kaiserWithGraph()));
      orch.processQuery('where is the blood place');
      orch.processQuery('I see the glass building');
      expect(orch.state.currentLocation, isNotNull);
      orch.state.reset();
      expect(orch.state.currentLocation, isNull);
    });

    test('reorientation defers when query also names a different dept', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(kaiserWithGraph()));
      orch.processQuery('where is the blood place'); // sets lab
      // "pediatrics" names a different dept; even though "building 5" is
      // a topology keyword, lookup should win.
      final result = orch.processQuery('actually pediatrics in building 5');
      expect(result, isA<Resolved>());
      expect((result as Resolved).department.name, 'Pediatrics');
    });

    test('switching dept clears currentLocation', () {
      final orch = QueryOrchestrator(tools: WayfindingTools(kaiserWithGraph()));
      orch.processQuery('where is the blood place');
      orch.processQuery('I see the glass building');
      expect(orch.state.currentLocation, isNotNull);
      // New dept lookup — should drop the stale anchor.
      orch.processQuery('actually pediatrics');
      expect(orch.state.currentLocation, isNull);
    });
  });
}

/// Small synthetic Kaiser-like graph for routing tests.
/// Geometry approximates the real campus: cantara on the west, ventura
/// on the east, buildings 2-3-4-5-6 strung between them with a fountain
/// detour off the main path.
CampusGraph _buildTestGraph({bool blockBuildingThreeToFour = false}) {
  final nodes = <TopologyNode>[
    const TopologyNode(
      id: 'cantara_parking',
      type: NodeType.parking,
      label: 'Cantara Street Parking Structures',
      description: 'West-side parking',
      keywords: ['cantara', 'cantara parking'],
      lat: 34.22890,
      lng: -118.44560,
    ),
    const TopologyNode(
      id: 'ventura_parking',
      type: NodeType.parking,
      label: 'Ventura Canyon Parking',
      description: 'East-side parking',
      keywords: ['ventura', 'ventura parking'],
      lat: 34.22790,
      lng: -118.44280,
    ),
    const TopologyNode(
      id: 'building_2_entrance',
      type: NodeType.entrance,
      label: 'Building 2',
      description: '',
      keywords: ['building 2', 'b2'],
      lat: 34.22878,
      lng: -118.44520,
    ),
    const TopologyNode(
      id: 'building_3_entrance',
      type: NodeType.entrance,
      label: 'Building 3',
      description: '',
      keywords: ['building 3', 'b3'],
      lat: 34.22865,
      lng: -118.44480,
    ),
    const TopologyNode(
      id: 'building_4_entrance',
      type: NodeType.entrance,
      label: 'Building 4',
      description: '',
      keywords: ['building 4', 'b4'],
      lat: 34.22852,
      lng: -118.44440,
    ),
    const TopologyNode(
      id: 'building_5_entrance',
      type: NodeType.entrance,
      label: 'Building 5',
      description: 'Glass atrium',
      keywords: ['building 5', 'b5', 'glass building', 'glass atrium', 'glass front'],
      lat: 34.22830,
      lng: -118.44390,
    ),
    const TopologyNode(
      id: 'building_6_entrance',
      type: NodeType.entrance,
      label: 'Building 6',
      description: '',
      keywords: ['building 6', 'b6'],
      lat: 34.22815,
      lng: -118.44350,
    ),
    const TopologyNode(
      id: 'hospital_main_entrance',
      type: NodeType.entrance,
      label: 'Hospital',
      description: '',
      keywords: ['hospital'],
      lat: 34.22800,
      lng: -118.44310,
    ),
    const TopologyNode(
      id: 'fountain_courtyard',
      type: NodeType.landmark,
      label: 'Fountain courtyard',
      description: '',
      keywords: ['fountain', 'courtyard'],
      lat: 34.22858,
      lng: -118.44460,
    ),
  ];

  final edges = <TopologyEdge>[
    const TopologyEdge(
      from: 'cantara_parking',
      to: 'building_2_entrance',
      distanceMeters: 60,
      walkMinutes: 1,
      instruction: 'Walk to Building 2',
    ),
    const TopologyEdge(
      from: 'cantara_parking',
      to: 'building_3_entrance',
      distanceMeters: 80,
      walkMinutes: 1.5,
      instruction: 'Walk to Building 3',
    ),
    TopologyEdge(
      from: 'building_3_entrance',
      to: 'building_4_entrance',
      distanceMeters: 50,
      walkMinutes: 0.8,
      instruction: 'Building 4 is next',
      blocked: blockBuildingThreeToFour,
    ),
    const TopologyEdge(
      from: 'building_3_entrance',
      to: 'fountain_courtyard',
      distanceMeters: 30,
      walkMinutes: 0.5,
      instruction: 'Walk to fountain',
    ),
    const TopologyEdge(
      from: 'fountain_courtyard',
      to: 'building_4_entrance',
      distanceMeters: 25,
      walkMinutes: 0.4,
      instruction: 'Past fountain to Building 4',
    ),
    const TopologyEdge(
      from: 'building_4_entrance',
      to: 'building_5_entrance',
      distanceMeters: 80,
      walkMinutes: 1.3,
      instruction: 'Cross campus to Building 5',
    ),
    const TopologyEdge(
      from: 'building_5_entrance',
      to: 'building_6_entrance',
      distanceMeters: 50,
      walkMinutes: 0.8,
      instruction: 'Building 6 is next',
    ),
    const TopologyEdge(
      from: 'ventura_parking',
      to: 'building_5_entrance',
      distanceMeters: 90,
      walkMinutes: 1.5,
      instruction: 'Building 5 to your left',
    ),
    const TopologyEdge(
      from: 'ventura_parking',
      to: 'building_6_entrance',
      distanceMeters: 60,
      walkMinutes: 1.0,
      instruction: 'Building 6 ahead',
    ),
    const TopologyEdge(
      from: 'ventura_parking',
      to: 'hospital_main_entrance',
      distanceMeters: 110,
      walkMinutes: 1.7,
      instruction: 'Hospital to your left',
    ),
  ];

  final adjacency = <String, List<TopologyEdge>>{};
  for (final e in edges) {
    (adjacency[e.from] ??= []).add(e);
  }
  return CampusGraph(
    facilityId: 'kaiser_panorama_city',
    version: 'test',
    nodes: {for (final n in nodes) n.id: n},
    adjacency: adjacency,
  );
}
