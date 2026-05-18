import 'package:flutter_test/flutter_test.dart';

import 'package:health_wayfinder/app.dart';

void main() {
  testWidgets('App renders home screen', (WidgetTester tester) async {
    await tester.pumpWidget(const HealthWayfinderApp());
    await tester.pumpAndSettle();

    expect(find.text('Where do you\nneed to go?'), findsOneWidget);
  });
}
