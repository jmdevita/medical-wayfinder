import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../models/topology.dart';

/// Result of resolving the user's starting node on the campus graph.
sealed class LocationOrigin {
  const LocationOrigin();
}

/// GPS produced a fix and we snapped it to a topology node.
class LocationResolved extends LocationOrigin {
  final TopologyNode node;
  final double accuracyMeters;
  const LocationResolved(this.node, this.accuracyMeters);
}

/// Location services are off device-wide, or the user denied permission.
/// Caller should fall back to the chip picker.
class LocationDenied extends LocationOrigin {
  const LocationDenied();
}

/// GPS was permitted but failed (timeout, hardware error). Same fallback
/// as denied, but worth distinguishing for debug logs.
class LocationUnavailable extends LocationOrigin {
  final String reason;
  const LocationUnavailable(this.reason);
}

/// Permission/fix succeeded but the topology has no nodes with lat/lng —
/// indoor-only graphs, missing geo data. Falls back to picker too.
class LocationNoNodes extends LocationOrigin {
  const LocationNoNodes();
}

/// Got a GPS fix but it's too far from any topology node to be the
/// patient's actual starting point — they're testing from home,
/// they're in a different city, or GPS drifted badly. We refuse to
/// snap and let the caller fall back to the picker.
class LocationOffCampus extends LocationOrigin {
  final double distanceMeters;
  const LocationOffCampus(this.distanceMeters);
}

/// One-shot, just-in-time GPS resolver. No background tracking, no
/// streaming. Caches the most recent successful fix for the lifetime of
/// the process (resolveOrigin treats anything fresher than [_cacheTtl] as
/// reusable) so a chatty session doesn't re-prompt the OS for fixes.
class LocationService {
  LocationService._();
  static final LocationService instance = LocationService._();

  static const _cacheTtl = Duration(seconds: 30);
  static const _fixTimeout = Duration(seconds: 8);
  // Max distance from the user's fix to the nearest topology node before
  // we reject the snap as nonsense. Covers being in the parking lot or
  // a nearby coffee shop; rejects wrong-city / wrong-continent.
  static const _offCampusThresholdMeters = 1000.0;

  Position? _cachedFix;
  DateTime? _cachedAt;

  Future<LocationOrigin> resolveOrigin(CampusGraph graph) async {
    final hasGeoNodes = graph.nodes.values.any(
      (n) => n.lat != null && n.lng != null,
    );
    if (!hasGeoNodes) return const LocationNoNodes();

    final Position? pos;
    try {
      pos = await _getFix();
    } on _PermissionRefused catch (e) {
      debugPrint('[location] permission refused: ${e.message}');
      return const LocationDenied();
    } catch (e) {
      debugPrint('[location] fix failed: $e');
      return LocationUnavailable(e.toString());
    }
    if (pos == null) return const LocationUnavailable('no position');

    return snapToGraph(graph, pos.latitude, pos.longitude,
        accuracyMeters: pos.accuracy);
  }

  /// Snap an arbitrary (lat, lng) — from GPS or a photo's EXIF — onto
  /// the campus graph, applying the same off-campus threshold as the
  /// live GPS path. Pure / synchronous; safe to call from the photo flow.
  LocationOrigin snapToGraph(
    CampusGraph graph,
    double lat,
    double lng, {
    double accuracyMeters = 0,
  }) {
    final hasGeoNodes = graph.nodes.values.any(
      (n) => n.lat != null && n.lng != null,
    );
    if (!hasGeoNodes) return const LocationNoNodes();
    final node = _nearestNode(graph, lat, lng);
    if (node == null) return const LocationNoNodes();
    final distM = haversineMeters(lat, lng, node.lat!, node.lng!);
    if (distM > _offCampusThresholdMeters) {
      return LocationOffCampus(distM);
    }
    return LocationResolved(node, accuracyMeters);
  }

  Future<Position?> _getFix() async {
    final cached = _cachedFix;
    final at = _cachedAt;
    if (cached != null &&
        at != null &&
        DateTime.now().difference(at) < _cacheTtl) {
      return cached;
    }

    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw const _PermissionRefused('location services disabled');
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      throw _PermissionRefused('permission=$permission');
    }

    final pos = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: _fixTimeout,
      ),
    );
    _cachedFix = pos;
    _cachedAt = DateTime.now();
    return pos;
  }

  TopologyNode? _nearestNode(CampusGraph graph, double lat, double lng) {
    TopologyNode? best;
    double bestDist = double.infinity;
    for (final node in graph.nodes.values) {
      if (node.lat == null || node.lng == null) continue;
      final d = haversineMeters(lat, lng, node.lat!, node.lng!);
      if (d < bestDist) {
        bestDist = d;
        best = node;
      }
    }
    return best;
  }

  @visibleForTesting
  void clearCache() {
    _cachedFix = null;
    _cachedAt = null;
  }
}

class _PermissionRefused implements Exception {
  final String message;
  const _PermissionRefused(this.message);
  @override
  String toString() => 'PermissionRefused: $message';
}
