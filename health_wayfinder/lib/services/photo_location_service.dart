import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';

import '../l10n/generated/app_localizations.dart';

class BuildingLocation {
  final String name;
  final double lat;
  final double lng;

  const BuildingLocation({
    required this.name,
    required this.lat,
    required this.lng,
  });
}

class PhotoLocationResult {
  final double? photoLat;
  final double? photoLng;
  final BuildingLocation? nearestBuilding;
  final double? distanceMeters;
  final Uint8List? imageBytes;

  const PhotoLocationResult({
    this.photoLat,
    this.photoLng,
    this.nearestBuilding,
    this.distanceMeters,
    this.imageBytes,
  });

  bool get hasGps => photoLat != null && photoLng != null;
  bool get hasMatch => nearestBuilding != null;
}

class PhotoLocationService {
  static final PhotoLocationService _instance = PhotoLocationService._();
  static PhotoLocationService get instance => _instance;
  PhotoLocationService._();

  final _picker = ImagePicker();

  /// Pick a photo from camera or gallery, extract GPS, find nearest building
  Future<PhotoLocationResult?> pickAndLocate({
    required String facilityDataJson,
    bool useCamera = true,
  }) async {
    try {
      final image = await _picker.pickImage(
        source: useCamera ? ImageSource.camera : ImageSource.gallery,
        maxWidth: 1024,
      );
      if (image == null) return null;

      final bytes = await image.readAsBytes();

      // Try to extract GPS from EXIF
      final gps = _extractGpsFromExif(bytes);

      // Parse building locations from facility JSON
      final buildings = _parseBuildingLocations(facilityDataJson);

      if (gps != null && buildings.isNotEmpty) {
        // Find nearest building
        BuildingLocation? nearest;
        double? minDist;
        for (final b in buildings) {
          final dist = _haversineDistance(gps.$1, gps.$2, b.lat, b.lng);
          if (minDist == null || dist < minDist) {
            minDist = dist;
            nearest = b;
          }
        }

        return PhotoLocationResult(
          photoLat: gps.$1,
          photoLng: gps.$2,
          nearestBuilding: nearest,
          distanceMeters: minDist,
          imageBytes: bytes,
        );
      }

      // No GPS data — return image bytes for Gemma multimodal
      return PhotoLocationResult(imageBytes: bytes);
    } catch (e) {
      debugPrint('[PhotoLocationService] Error: $e');
      return null;
    }
  }

  /// Extract GPS coordinates from EXIF data in JPEG
  /// Returns (lat, lng) or null if not found
  (double, double)? _extractGpsFromExif(Uint8List bytes) {
    try {
      // Look for EXIF APP1 marker (FFE1) in JPEG
      if (bytes.length < 4 || bytes[0] != 0xFF || bytes[1] != 0xD8) {
        return null; // Not a JPEG
      }

      int offset = 2;
      while (offset < bytes.length - 4) {
        if (bytes[offset] != 0xFF) break;
        final marker = bytes[offset + 1];
        final segmentLength = (bytes[offset + 2] << 8) | bytes[offset + 3];

        if (marker == 0xE1) {
          // APP1 — potential EXIF
          final end = offset + 2 + segmentLength;
          if (end > bytes.length) break;
          final exifData = bytes.sublist(offset + 4, end);
          final gps = _parseExifGps(exifData);
          if (gps != null) return gps;
        }

        offset += 2 + segmentLength;
      }
    } catch (e) {
      debugPrint('[PhotoLocationService] EXIF parse error: $e');
    }
    return null;
  }

  /// Parse GPS data from EXIF segment
  (double, double)? _parseExifGps(Uint8List exifData) {
    // Check for "Exif\0\0" header
    if (exifData.length < 14) return null;
    final header = String.fromCharCodes(exifData.sublist(0, 4));
    if (header != 'Exif') return null;

    // Determine byte order
    final tiffOffset = 6;
    if (exifData.length < tiffOffset + 8) return null;
    final byteOrder = (exifData[tiffOffset] << 8) | exifData[tiffOffset + 1];
    final isLittleEndian = byteOrder == 0x4949;

    int readU16(int pos) {
      if (pos + 1 >= exifData.length) return 0;
      return isLittleEndian
          ? exifData[pos] | (exifData[pos + 1] << 8)
          : (exifData[pos] << 8) | exifData[pos + 1];
    }

    int readU32(int pos) {
      if (pos + 3 >= exifData.length) return 0;
      return isLittleEndian
          ? exifData[pos] |
              (exifData[pos + 1] << 8) |
              (exifData[pos + 2] << 16) |
              (exifData[pos + 3] << 24)
          : (exifData[pos] << 24) |
              (exifData[pos + 1] << 16) |
              (exifData[pos + 2] << 8) |
              exifData[pos + 3];
    }

    double readRational(int pos) {
      final num = readU32(pos);
      final den = readU32(pos + 4);
      return den == 0 ? 0 : num / den;
    }

    // Find GPS IFD pointer from IFD0
    final ifd0Offset = tiffOffset + readU32(tiffOffset + 4);
    if (ifd0Offset >= exifData.length) return null;

    final ifd0Count = readU16(ifd0Offset);
    int? gpsIfdOffset;

    for (var i = 0; i < ifd0Count; i++) {
      final entryOffset = ifd0Offset + 2 + (i * 12);
      if (entryOffset + 12 > exifData.length) break;
      final tag = readU16(entryOffset);
      if (tag == 0x8825) {
        // GPSInfoIFDPointer
        gpsIfdOffset = tiffOffset + readU32(entryOffset + 8);
        break;
      }
    }

    if (gpsIfdOffset == null || gpsIfdOffset >= exifData.length) return null;

    // Parse GPS IFD
    final gpsCount = readU16(gpsIfdOffset);
    String? latRef, lngRef;
    double? lat, lng;

    for (var i = 0; i < gpsCount; i++) {
      final entryOffset = gpsIfdOffset + 2 + (i * 12);
      if (entryOffset + 12 > exifData.length) break;
      final tag = readU16(entryOffset);
      final valueOffset = tiffOffset + readU32(entryOffset + 8);

      switch (tag) {
        case 0x0001: // GPSLatitudeRef
          latRef = String.fromCharCode(exifData[entryOffset + 8]);
          break;
        case 0x0002: // GPSLatitude
          if (valueOffset + 24 <= exifData.length) {
            final d = readRational(valueOffset);
            final m = readRational(valueOffset + 8);
            final s = readRational(valueOffset + 16);
            lat = d + m / 60 + s / 3600;
          }
          break;
        case 0x0003: // GPSLongitudeRef
          lngRef = String.fromCharCode(exifData[entryOffset + 8]);
          break;
        case 0x0004: // GPSLongitude
          if (valueOffset + 24 <= exifData.length) {
            final d = readRational(valueOffset);
            final m = readRational(valueOffset + 8);
            final s = readRational(valueOffset + 16);
            lng = d + m / 60 + s / 3600;
          }
          break;
      }
    }

    if (lat != null && lng != null) {
      if (latRef == 'S') lat = -lat;
      if (lngRef == 'W') lng = -lng;
      return (lat, lng);
    }

    return null;
  }

  /// Parse building locations from facility JSON
  List<BuildingLocation> _parseBuildingLocations(String jsonStr) {
    try {
      final data = json.decode(jsonStr) as Map<String, dynamic>;
      final buildings = data['buildings'] as List<dynamic>?;
      if (buildings == null) return [];

      return buildings.map((b) {
        return BuildingLocation(
          name: b['name'] as String,
          lat: (b['lat'] as num).toDouble(),
          lng: (b['lng'] as num).toDouble(),
        );
      }).toList();
    } catch (e) {
      return [];
    }
  }

  /// Haversine distance in meters between two GPS points
  double _haversineDistance(double lat1, double lon1, double lat2, double lon2) {
    const R = 6371000.0; // Earth radius in meters
    final dLat = _toRadians(lat2 - lat1);
    final dLon = _toRadians(lon2 - lon1);
    final a = sin(dLat / 2) * sin(dLat / 2) +
        cos(_toRadians(lat1)) * cos(_toRadians(lat2)) *
        sin(dLon / 2) * sin(dLon / 2);
    final c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return R * c;
  }

  double _toRadians(double degrees) => degrees * pi / 180;

  /// Generate a guide response from a photo location result
  String buildLocationResponse(PhotoLocationResult result, {AppLocalizations? l10n}) {
    if (result.hasMatch) {
      final dist = result.distanceMeters!;
      final building = result.nearestBuilding!.name;
      if (dist < 30) {
        return l10n?.photoAtBuilding(building) ??
            "Based on your photo's location, you're right at $building! Look for the entrance nearby.";
      } else if (dist < 100) {
        return l10n?.photoNearBuilding(dist.round(), building) ??
            "Based on your photo's location, you're about ${dist.round()} meters from $building. You're close — keep heading toward it.";
      } else {
        return l10n?.photoHeadTowardBuilding(dist.round(), building) ??
            "Based on your photo's location, you're about ${dist.round()} meters from $building. Head in that direction.";
      }
    } else if (!result.hasGps) {
      return l10n?.photoNoLocationData ??
          "I couldn't find location data in that photo. Try taking a photo with your camera — it will include GPS coordinates that help me find where you are.";
    }
    return l10n?.photoLocationTrouble ??
        "I'm having trouble determining your location from that photo.";
  }
}
