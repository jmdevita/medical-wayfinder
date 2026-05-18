import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_wayfinder/models/facility.dart';
import 'package:health_wayfinder/models/guide_message.dart';
import 'package:health_wayfinder/services/response_parser.dart';

void main() {
  // -----------------------------------------------------------
  // Contract alignment: every block type in data_contract.json
  // must be handled by the parser
  // -----------------------------------------------------------

  group('destination block', () {
    test('parses valid destination', () {
      final input = jsonEncode([
        {
          'type': 'destination',
          'department': 'Lab / Blood Draw',
          'building': 'Building 3',
          'floor': 'Basement',
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.destinationCard);
      expect(result[0].department!.name, 'Lab / Blood Draw');
      expect(result[0].department!.building, 'Building 3');
      expect(result[0].department!.floor, 'Basement');
    });

    test('rejects destination missing required fields', () {
      final input = jsonEncode([
        {'type': 'destination', 'department': 'Lab'}
      ]);
      final result = ResponseParser.parse(input);
      // Missing building + floor -> block dropped -> fallback to raw
      expect(result[0].type, GuideMessageType.guideText);
    });
  });

  group('steps block', () {
    test('parses valid steps with accessibility badges', () {
      final input = jsonEncode([
        {
          'type': 'steps',
          'steps': [
            {'text': 'Walk to the front door', 'accessibility': null},
            {
              'text': 'Take the elevator to floor 2',
              'accessibility': 'elevator'
            },
            {
              'text': 'Enter through automatic doors',
              'accessibility': 'automatic_doors'
            },
            {'text': 'Use the ramp on the left', 'accessibility': 'ramp'},
            {
              'text': 'Go through accessible entrance',
              'accessibility': 'accessible_entrance'
            },
            {'text': 'You have arrived', 'accessibility': 'arrived'},
          ]
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.stepCarousel);
      final steps = result[0].steps!;
      expect(steps, hasLength(6));

      // null badge
      expect(steps[0].accessibilityBadge, isNull);
      // Badges from the data-contract enums get translated to display labels
      // so the carousel doesn't render raw snake_case ("automatic_doors").
      expect(steps[1].accessibilityBadge, 'Elevator');
      expect(steps[2].accessibilityBadge, 'Automatic doors');
      expect(steps[3].accessibilityBadge, 'Ramp');
      expect(steps[4].accessibilityBadge, 'Accessible entrance');
      expect(steps[5].accessibilityBadge, "You've arrived");

      // step numbers are 1-indexed
      expect(steps[0].number, 1);
      expect(steps[5].number, 6);
    });

    test('strips invalid accessibility badge', () {
      final input = jsonEncode([
        {
          'type': 'steps',
          'steps': [
            {'text': 'Walk forward', 'accessibility': 'jetpack'}
          ]
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result[0].steps![0].accessibilityBadge, isNull);
    });

    test('rejects steps with empty array', () {
      final input = jsonEncode([
        {'type': 'steps', 'steps': []}
      ]);
      final result = ResponseParser.parse(input);
      expect(result[0].type, GuideMessageType.guideText);
    });
  });

  group('disambig block', () {
    test('parses valid disambig with 2+ options', () {
      final input = jsonEncode([
        {
          'type': 'disambig',
          'question': 'Which department?',
          'options': ['Primary Care', 'Urgent Care', 'Pediatrics']
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.disambigCard);
      expect(result[0].options, hasLength(3));
      expect(result[0].options![0].name, 'Primary Care');
    });

    test('rejects disambig with fewer than 2 options', () {
      final input = jsonEncode([
        {
          'type': 'disambig',
          'question': 'Which department?',
          'options': ['Only one']
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result[0].type, GuideMessageType.guideText);
    });

    test('surfaces the data-contract question on the GuideMessage', () {
      final input = jsonEncode([
        {
          'type': 'disambig',
          'question': 'What type of imaging do you need?',
          'options': ['MRI', 'X-ray', 'Ultrasound']
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result[0].text, 'What type of imaging do you need?');
    });

    test('leaves question null when missing or blank, so UI can fall back', () {
      final input = jsonEncode([
        {
          'type': 'disambig',
          'question': '   ',
          'options': ['A', 'B']
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result[0].text, isNull);
    });

    test('resolves options against facility departments, preserving directionsMap', () {
      final realDept = Department(
        name: 'MRI / CT Scan / Ultrasound',
        building: 'Building 5',
        floor: 'Ground floor',
        directionsMap: const {'from_ventura': 'Exit Ventura Canyon parking...'},
      );
      final facility = Facility(
        id: 'kaiser_panorama_city',
        name: 'Kaiser',
        address: '',
        type: 'hospital',
        departments: [
          const Department(name: 'X-ray / Bone Density (DEXA)', building: 'Building 3', floor: 'Basement'),
          realDept,
        ],
      );
      final input = jsonEncode([
        {
          'type': 'disambig',
          'question': 'Which imaging?',
          'options': ['X-ray / Bone Density (DEXA)', 'MRI / CT Scan / Ultrasound'],
        }
      ]);
      final result = ResponseParser.parse(input, facility: facility);
      final opts = result[0].options!;
      expect(opts[0].building, 'Building 3');
      expect(opts[1].building, 'Building 5');
      expect(opts[1].directionsMap, isNotEmpty);
    });

    test('falls back to synthetic Department when option does not match', () {
      final facility = Facility(
        id: 'x', name: 'X', address: '', type: 'clinic',
        departments: const [Department(name: 'Pharmacy', building: 'A', floor: '1')],
      );
      final input = jsonEncode([
        {
          'type': 'disambig',
          'question': '?',
          'options': ['Unknown Dept', 'Pharmacy'],
        }
      ]);
      final result = ResponseParser.parse(input, facility: facility);
      final opts = result[0].options!;
      expect(opts[0].name, 'Unknown Dept');
      expect(opts[0].building, ''); // synthetic
      expect(opts[1].building, 'A'); // matched
    });
  });

  group('guide_text block', () {
    test('parses valid guide_text', () {
      final input = jsonEncode([
        {'type': 'guide_text', 'text': 'How can I help you today?'}
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.guideText);
      expect(result[0].text, 'How can I help you today?');
    });

    test('rejects guide_text with empty text', () {
      final input = jsonEncode([
        {'type': 'guide_text', 'text': ''}
      ]);
      final result = ResponseParser.parse(input);
      // Empty text -> block dropped -> fallback to raw
      expect(result[0].type, GuideMessageType.guideText);
      // Fallback text is the raw JSON, not empty string
      expect(result[0].text, isNot(''));
    });
  });

  group('arrival block', () {
    test('parses valid arrival', () {
      final input = jsonEncode([
        {
          'type': 'arrival',
          'check_in': 'Check in at the front desk with your ID.'
        }
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.arrival);
      expect(
          result[0].checkInText, 'Check in at the front desk with your ID.');
    });

    test('rejects arrival missing check_in', () {
      final input = jsonEncode([
        {'type': 'arrival'}
      ]);
      final result = ResponseParser.parse(input);
      expect(result[0].type, GuideMessageType.guideText);
    });
  });

  // -----------------------------------------------------------
  // Multi-block responses (contract says destination + steps + arrival together)
  // -----------------------------------------------------------

  group('multi-block response', () {
    test('parses full direction response (destination + steps + arrival)', () {
      final input = jsonEncode([
        {
          'type': 'destination',
          'department': 'Radiology',
          'building': 'Building 5',
          'floor': '2nd Floor'
        },
        {
          'type': 'steps',
          'steps': [
            {'text': 'Walk east from parking', 'accessibility': null},
            {
              'text': 'Enter through the ramp on the right',
              'accessibility': 'ramp'
            },
            {'text': 'Radiology is on the left', 'accessibility': 'arrived'},
          ]
        },
        {
          'type': 'arrival',
          'check_in': 'Check in at the Radiology window.'
        },
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(3));
      expect(result[0].type, GuideMessageType.destinationCard);
      expect(result[1].type, GuideMessageType.stepCarousel);
      expect(result[2].type, GuideMessageType.arrival);
    });
  });

  // -----------------------------------------------------------
  // Graceful degradation
  // -----------------------------------------------------------

  group('graceful degradation', () {
    test('falls back to guideText for non-JSON input', () {
      final result = ResponseParser.parse('Sorry, I could not understand.');
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.guideText);
      expect(result[0].text, 'Sorry, I could not understand.');
    });

    test('falls back to guideText for non-array JSON', () {
      final result = ResponseParser.parse('{"type": "guide_text"}');
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.guideText);
    });

    test('falls back to guideText for empty array', () {
      final result = ResponseParser.parse('[]');
      expect(result, hasLength(1));
      expect(result[0].type, GuideMessageType.guideText);
    });

    test('skips unknown block types without crashing', () {
      final input = jsonEncode([
        {'type': 'unknown_future_type', 'data': 'something'},
        {'type': 'guide_text', 'text': 'Hello'},
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(1));
      expect(result[0].text, 'Hello');
    });

    test('skips blocks without type field', () {
      final input = jsonEncode([
        {'text': 'no type field here'},
        {'type': 'guide_text', 'text': 'Hello'},
      ]);
      final result = ResponseParser.parse(input);
      expect(result, hasLength(1));
      expect(result[0].text, 'Hello');
    });
  });
}
