import 'package:flutter/foundation.dart';
import 'package:json_repair_flutter/json_repair_flutter.dart';

import '../l10n/generated/app_localizations.dart';
import '../models/facility.dart';
import '../models/guide_message.dart';
import '../models/step.dart';

/// Parses raw JSON from the Gemma model into GuideMessage objects.
///
/// Implements the data contract defined in:
///   training/data/prompts/data_contract.json
///
/// Valid block types: destination, steps, disambig, guide_text, arrival
/// See data_contract.json for required fields and allowed values.

const _validAccessibilityBadges = {
  'elevator',
  'ramp',
  'automatic_doors',
  'accessible_entrance',
  'arrived',
};

/// Display labels for the data-contract badge enums. The contract uses
/// snake_case ids; the UI shows human-readable text. Falls back to English
/// when [l10n] is null (tests, error paths).
String _badgeLabel(String id, AppLocalizations? l10n) {
  switch (id) {
    case 'elevator':
      return l10n?.badgeElevator ?? 'Elevator';
    case 'ramp':
      return l10n?.badgeRamp ?? 'Ramp';
    case 'automatic_doors':
      return l10n?.badgeAutomaticDoors ?? 'Automatic doors';
    case 'accessible_entrance':
      return l10n?.badgeAccessibleEntrance ?? 'Accessible entrance';
    case 'arrived':
      return l10n?.youveArrived ?? "You've arrived";
  }
  return id;
}

class ResponseParser {
  /// Parse a raw model response string into a list of GuideMessages.
  ///
  /// [facility] (optional) is the active facility. When supplied, disambig
  /// option strings are resolved against this facility's `departments[]`
  /// list so that user-tap selections carry the real `Department` (with
  /// `directionsMap`, `building`, `floor`, `topologyNodeId`) into the
  /// orchestrator. Without it, options degrade to synthetic name-only
  /// `Department` objects and `getDirections` returns empty.
  ///
  /// Returns an error GuideMessage if parsing fails.
  static List<GuideMessage> parse(
    String raw, {
    AppLocalizations? l10n,
    Facility? facility,
  }) {
    // Use json_repair_flutter: tries strict jsonDecode first, falls back
    // to a forgiving parser that handles truncation, missing brackets,
    // trailing commas, code fences, and prose around the JSON.
    dynamic decoded;
    try {
      decoded = repairJson(raw);
    } catch (e) {
      debugPrint('[ResponseParser] repairJson failed: $e');
      return [GuideMessage.guideText(raw)];
    }

    // Models sometimes wrap the array as {"blocks": [...]} or emit a
    // single block object. Normalize to a List.
    final List<dynamic> blocks;
    if (decoded is List) {
      blocks = decoded;
    } else if (decoded is Map<String, dynamic>) {
      if (decoded['type'] is String) {
        blocks = [decoded];
      } else {
        final wrapped = decoded.values
            .firstWhere((v) => v is List, orElse: () => null);
        if (wrapped is List) {
          blocks = wrapped;
        } else {
          return [GuideMessage.guideText(raw)];
        }
      }
    } else {
      return [GuideMessage.guideText(raw)];
    }

    if (blocks.isEmpty) {
      return [GuideMessage.guideText(raw)];
    }

    final messages = <GuideMessage>[];
    for (final block in blocks) {
      if (block is! Map<String, dynamic>) continue;
      final msg = _parseBlock(block, l10n, facility);
      if (msg != null) messages.add(msg);
    }

    if (messages.isEmpty) {
      return [GuideMessage.guideText(raw)];
    }
    return messages;
  }

  static GuideMessage? _parseBlock(
    Map<String, dynamic> block,
    AppLocalizations? l10n,
    Facility? facility,
  ) {
    final type = block['type'] as String?;
    if (type == null) return null;

    switch (type) {
      case 'destination':
        return _parseDestination(block);
      case 'steps':
        return _parseSteps(block, l10n);
      case 'disambig':
        return _parseDisambig(block, facility);
      case 'guide_text':
        return _parseGuideText(block);
      case 'arrival':
        return _parseArrival(block);
      default:
        return null;
    }
  }

  static GuideMessage? _parseDestination(Map<String, dynamic> block) {
    final department = block['department'] as String?;
    final building = block['building'] as String?;
    // Model sometimes emits `null` for floor when the source has no floor;
    // the data contract says use empty string. Coerce null -> "" so the
    // destination still renders instead of dropping the whole block.
    final floor = block['floor'] as String? ?? '';
    if (department == null || building == null) return null;

    return GuideMessage.destination(Department(
      name: department,
      building: building,
      floor: floor,
    ));
  }

  static GuideMessage? _parseSteps(Map<String, dynamic> block, AppLocalizations? l10n) {
    final stepsRaw = block['steps'] as List?;
    if (stepsRaw == null || stepsRaw.isEmpty) return null;

    final steps = <WalkingStep>[];
    for (var i = 0; i < stepsRaw.length; i++) {
      final s = stepsRaw[i];
      if (s is! Map<String, dynamic>) continue;
      final text = s['text'] as String?;
      if (text == null || text.isEmpty) continue;

      final badge = s['accessibility'] as String?;
      steps.add(WalkingStep(
        number: i + 1,
        text: text,
        accessibilityBadge:
            badge != null && _validAccessibilityBadges.contains(badge)
                ? _badgeLabel(badge, l10n)
                : null,
      ));
    }

    if (steps.isEmpty) return null;
    return GuideMessage.steps(steps);
  }

  static GuideMessage? _parseDisambig(
    Map<String, dynamic> block,
    Facility? facility,
  ) {
    final options = block['options'] as List?;
    if (options == null || options.length < 2) return null;

    final departments = options
        .whereType<String>()
        .map((name) => _resolveOption(name, facility))
        .toList();

    if (departments.length < 2) return null;

    final question = block['question'] as String?;
    return GuideMessage.disambig(
      departments,
      question: question != null && question.trim().isNotEmpty ? question : null,
    );
  }

  /// Resolve a disambig option string against the active facility's
  /// `departments[]` list, so the resulting `Department` carries
  /// `directionsMap`, `building`, `floor`, and `topologyNodeId` for the
  /// orchestrator. Falls back to a synthetic name-only Department when
  /// there's no facility context or no match — the contract allows
  /// arbitrary strings, but a name match is what the orchestrator needs.
  static Department _resolveOption(String option, Facility? facility) {
    if (facility == null) {
      return Department(name: option, building: '', floor: '');
    }
    for (final dept in facility.departments) {
      if (dept.name == option) return dept;
    }
    // Case-insensitive fallback for whitespace / capitalization drift.
    final needle = option.toLowerCase().trim();
    for (final dept in facility.departments) {
      if (dept.name.toLowerCase().trim() == needle) return dept;
    }
    return Department(name: option, building: '', floor: '');
  }

  static GuideMessage? _parseGuideText(Map<String, dynamic> block) {
    final text = block['text'] as String?;
    if (text == null || text.isEmpty) return null;
    return GuideMessage.guideText(text);
  }

  static GuideMessage? _parseArrival(Map<String, dynamic> block) {
    final checkIn = block['check_in'] as String?;
    if (checkIn == null || checkIn.isEmpty) return null;
    return GuideMessage.arrival(checkInText: checkIn);
  }
}
