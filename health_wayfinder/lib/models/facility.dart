import 'topology.dart';

class Facility {
  final String id;
  final String name;
  final String address;
  final String type;
  final String? mainPhone;
  final double? distanceMiles;
  final List<Department> departments;
  final List<ParkingArea> parking;
  final String facilityDataJson;
  final CampusGraph? topology;

  const Facility({
    required this.id,
    required this.name,
    required this.address,
    required this.type,
    this.mainPhone,
    this.distanceMiles,
    this.departments = const [],
    this.parking = const [],
    this.facilityDataJson = '',
    this.topology,
  });
}

class Department {
  final String name;
  final String building;
  final String floor;
  final String? hours;
  final bool accessible;
  final List<String> aliases;
  final String? checkIn;
  /// All direction variants keyed by origin.
  /// Kaiser uses "from_cantara", "from_ventura"; JP uses "default".
  final Map<String, String> directionsMap;
  /// Optional explicit topology node id for the destination. Falls back
  /// to building-name match when null. Lets distinct departments in the
  /// same building (e.g. ER vs Radiology in "Hospital") route to the
  /// right entrance.
  final String? topologyNodeId;

  const Department({
    required this.name,
    required this.building,
    required this.floor,
    this.hours,
    this.accessible = true,
    this.aliases = const [],
    this.checkIn,
    this.directionsMap = const {},
    this.topologyNodeId,
  });

  /// Returns the first available directions string (backward compat).
  String? get directions =>
      directionsMap.isNotEmpty ? directionsMap.values.first : null;
}

class ParkingArea {
  final String name;
  final List<String> nearestBuildings;
  final String entranceNote;

  const ParkingArea({
    required this.name,
    required this.nearestBuildings,
    required this.entranceNote,
  });
}
