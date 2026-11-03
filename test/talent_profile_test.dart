import 'dart:convert';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/talent_profile_editor.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    'person validates and publishes their own volunteer profile on a phone',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      Map<String, dynamic>? published;
      final api = CompanyApiClient(
        client: MockClient((request) async {
          expect(request.method, 'PUT');
          expect(request.url.path, '/company/talent/profile');
          published = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({...published!, 'id': 'profile-1'}),
            200,
          );
        }),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => TalentProfileEditor(api: api),
                  ),
                ),
                child: const Text('Create profile'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Create profile'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Publish my profile'));
      await tester.tap(find.text('Publish my profile'));
      await tester.pumpAndSettle();
      expect(published, isNull);
      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'Alex');
      await tester.enterText(fields.at(1), 'Product designer');
      await tester.enterText(
        fields.at(2),
        'I help small teams design thoughtful digital products.',
      );
      await tester.enterText(fields.at(3), 'Design, Flutter');
      await tester.ensureVisible(find.text('Hourly rate · USD'));
      await tester.tap(find.text('Hourly rate · USD'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Volunteer · no charge').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Publish my profile'));
      await tester.tap(find.text('Publish my profile'));
      await tester.pumpAndSettle();
      expect(published?['name'], 'Alex');
      expect(published?['skills'], ['Design', 'Flutter']);
      expect(published?['pricing'], 'volunteer');
      expect(published?['rate'], 0);
      expect(published?['published'], isTrue);
      expect(find.text('Create profile'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
