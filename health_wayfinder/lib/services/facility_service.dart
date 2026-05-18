import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import '../models/facility.dart';
import '../models/topology.dart';

class FacilityService {
  static final FacilityService _instance = FacilityService._();
  static FacilityService get instance => _instance;
  FacilityService._();

  final Map<String, String> _cache = {};
  List<Facility>? _discoverCache;

  /// Optional alias map: facility-id used in code -> filename stem in
  /// assets/facilities/. Only needed when the two diverge. The default is
  /// "filename = id", so brand-new facilities don't need an entry here at all.
  static const _fileMap = <String, String>{};

  /// Discover every facility bundled in `assets/facilities/`. Reads the
  /// AssetManifest at startup, loads each `<slug>.json` (skipping
  /// `*.topology.json`), and returns lightweight `Facility` records suitable
  /// for the picker. Cached after the first call.
  ///
  /// To add a new facility: drop `assets/facilities/<slug>.json` (and an
  /// optional `<slug>.topology.json`). No Dart edits required.
  Future<List<Facility>> discoverFacilities() async {
    if (_discoverCache != null) return _discoverCache!;
    final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
    final keys = manifest.listAssets()
        .where((k) => k.startsWith('assets/facilities/')
            && k.endsWith('.json')
            && !k.endsWith('.topology.json'))
        .toList()
      ..sort();
    final out = <Facility>[];
    for (final key in keys) {
      try {
        final raw = await rootBundle.loadString(key);
        final data = json.decode(raw) as Map<String, dynamic>;
        out.add(Facility(
          id: (data['id'] as String?) ?? key.split('/').last.replaceAll('.json', ''),
          name: (data['name'] as String?) ?? '',
          address: (data['address'] as String?) ?? '',
          type: (data['type'] as String?) ?? '',
          mainPhone: data['main_phone'] as String?,
        ));
      } catch (e) {
        debugPrint('[FacilityService] Skipping $key: $e');
      }
    }
    _discoverCache = out;
    return out;
  }

  /// Load raw facility JSON for injection into Gemma system prompt
  Future<String> getFacilityData(String facilityId) async {
    if (_cache.containsKey(facilityId)) return _cache[facilityId]!;

    final filename = _fileMap[facilityId] ?? facilityId;
    try {
      final jsonStr = await rootBundle.loadString(
        'assets/facilities/$filename.json',
      );
      _cache[facilityId] = jsonStr;
      return jsonStr;
    } catch (e) {
      debugPrint('[FacilityService] Could not load $filename.json: $e');
      return '{}';
    }
  }

  /// Parse facility JSON into a Facility model with departments
  Future<Facility> loadFacility(String facilityId) async {
    final jsonStr = await getFacilityData(facilityId);

    late final Map<String, dynamic> data;
    try {
      data = json.decode(jsonStr) as Map<String, dynamic>;
    } catch (e) {
      debugPrint('[FacilityService] JSON parse error for $facilityId: $e');
      return Facility(id: facilityId, name: facilityId, address: '', type: '');
    }

    // If JSON was empty/missing, return a basic facility
    if (!data.containsKey('id')) {
      debugPrint('[FacilityService] No data for $facilityId, using empty facility');
      return Facility(id: facilityId, name: facilityId, address: '', type: '');
    }

    final departments = (data['departments'] as List<dynamic>? ?? [])
        .map((d) {
          final dirMap = <String, String>{};
          if (d['directions'] is String) {
            dirMap['default'] = d['directions'] as String;
          }
          if (d['directions_from_cantara'] is String) {
            dirMap['from_cantara'] = d['directions_from_cantara'] as String;
          }
          if (d['directions_from_ventura'] is String) {
            dirMap['from_ventura'] = d['directions_from_ventura'] as String;
          }
          return Department(
            name: (d['name'] as String?) ?? '',
            building: (d['building'] as String?) ?? '',
            floor: (d['floor'] as String?) ?? '',
            hours: d['hours'] as String?,
            accessible: (d['accessible'] as bool?) ?? true,
            aliases: (d['aliases'] as List<dynamic>?)
                    ?.map((a) => a.toString())
                    .toList() ??
                [],
            checkIn: d['check_in'] as String?,
            directionsMap: dirMap,
            topologyNodeId: d['topology_node_id'] as String?,
          );
        })
        .toList();

    final parking = (data['parking'] as List<dynamic>? ?? [])
        .map((p) => ParkingArea(
              name: (p['name'] as String?) ?? '',
              nearestBuildings: (p['nearest_buildings'] as List<dynamic>?)
                      ?.map((b) => b.toString())
                      .toList() ??
                  [],
              entranceNote: (p['entrance_note'] as String?) ?? '',
            ))
        .toList();

    final topology = await _loadTopology(facilityId);

    return Facility(
      id: (data['id'] as String?) ?? facilityId,
      name: (data['name'] as String?) ?? facilityId,
      address: (data['address'] as String?) ?? '',
      type: (data['type'] as String?) ?? '',
      mainPhone: data['main_phone'] as String?,
      departments: departments,
      parking: parking,
      facilityDataJson: jsonStr,
      topology: topology,
    );
  }

  Future<CampusGraph?> _loadTopology(String facilityId) async {
    final filename = _fileMap[facilityId] ?? facilityId;
    try {
      final jsonStr = await rootBundle.loadString(
        'assets/facilities/$filename.topology.json',
      );
      final data = json.decode(jsonStr) as Map<String, dynamic>;
      return CampusGraph.fromJson(data);
    } catch (e) {
      debugPrint('[FacilityService] No topology for $filename: $e');
      return null;
    }
  }
}
