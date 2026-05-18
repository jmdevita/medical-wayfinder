import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:health_wayfinder/l10n/generated/app_localizations.dart';
import 'package:health_wayfinder/models/facility.dart';
import 'package:health_wayfinder/screens/home_screen.dart';

Widget _wrap(Widget child) => MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('en'), Locale('es')],
      home: Scaffold(body: child),
    );

void main() {
  const placeholder = Facility(id: '', name: 'Loading…', address: '', type: '');

  testWidgets('HomeScreen shows empty-state when bootstrap fails', (tester) async {
    await tester.pumpWidget(_wrap(HomeScreen(
      facility: placeholder,
      facilities: const [],
      bootstrapFailed: true,
      onFacilityChanged: (_) {},
      onQuery: (_) {},
      textFocusNode: FocusNode(),
      needsAccessibility: false,
      onAccessibilityChanged: (_) {},
    )));
    await tester.pumpAndSettle();

    expect(find.text('No facilities available'), findsOneWidget);
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    // The normal home UI must not render.
    expect(find.text('Where do you\nneed to go?'), findsNothing);
    expect(find.byIcon(Icons.send), findsNothing);
  });

  testWidgets('HomeScreen renders normal UI when bootstrap succeeds', (tester) async {
    await tester.pumpWidget(_wrap(HomeScreen(
      facility: const Facility(
        id: 'kaiser_panorama_city',
        name: 'Kaiser Panorama City',
        address: '13651 Willard St',
        type: 'hospital',
      ),
      facilities: const [],
      bootstrapFailed: false,
      onFacilityChanged: (_) {},
      onQuery: (_) {},
      textFocusNode: FocusNode(),
      needsAccessibility: false,
      onAccessibilityChanged: (_) {},
    )));
    await tester.pumpAndSettle();

    expect(find.text('No facilities available'), findsNothing);
    expect(find.text('Where do you\nneed to go?'), findsOneWidget);
  });
}
