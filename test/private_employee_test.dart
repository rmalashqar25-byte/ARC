import 'dart:convert';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/pages/companypage/market.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    'add a private employee to Research without publishing a talent listing',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1280, 1000);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      Map<String, dynamic>? employee;
      var taskSaved = false;
      final api = CompanyApiClient(
        client: MockClient((request) async {
          if (request.url.path == '/company/humans') {
            if (request.method == 'POST') {
              employee = {
                ...jsonDecode(request.body) as Map<String, dynamic>,
                'id': 'employee-a',
              };
              return http.Response(jsonEncode(employee), 201);
            }
            expect(request.url.queryParameters['session_id'], 'project-a');
            return http.Response(
              jsonEncode({
                'employees': employee == null ? [] : [employee],
              }),
              200,
            );
          }
          if (request.url.path == '/company/human-tasks') {
            final body = jsonDecode(request.body) as Map;
            expect(body['employee_id'], 'employee-a');
            expect(body['session_id'], 'project-a');
            taskSaved = true;
            return http.Response(
              jsonEncode({'status': 'draft_assignment'}),
              201,
            );
          }
          fail(
            'Private employees must not use public talent APIs: ${request.url}',
          );
        }),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Market(api: api, sessionId: 'project-a'),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Research'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Your employees'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add my employee'));
      await tester.pumpAndSettle();
      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'Maya');
      await tester.enterText(fields.at(1), 'Research assistant');
      await tester.enterText(
        fields.at(2),
        'Helps our team organize evidence and competitor research.',
      );
      await tester.enterText(fields.at(3), 'Research, Writing');
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Maximum active jobs'),
        '2',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Your rate'),
        '25',
      );
      await tester.ensureVisible(find.text('Add employee to project'));
      await tester.tap(find.text('Add employee to project'));
      await tester.pumpAndSettle();
      expect(employee?['department'], 'research');
      expect(employee?['job_capacity'], 2);
      expect(employee?['session_id'], 'project-a');
      expect(employee?.containsKey('published'), isFalse);
      await tester.ensureVisible(find.text('Maya'));
      await tester.tap(find.text('Maya'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Prepare an employee task'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField).last,
        'Review our competitor research',
      );
      await tester.tap(find.text('Save project brief'));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 300));
      expect(taskSaved, isTrue);
      expect(tester.takeException(), isNull);
    },
  );
}
