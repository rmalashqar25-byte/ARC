import 'dart:convert';
import 'package:arc/frontend/pages/companypage/work_board.dart';
import 'package:arc/frontend/pages/human_work_portal.dart';
import 'package:arc/frontend/work_api.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    'human sees only their group and jobs, accepts and submits to manager on a phone',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      String status = 'offered', deliverable = '';
      final api = WorkApi(
        workerToken: 'synthetic-private-worker-link',
        client: MockClient((request) async {
          expect(
            request.headers['x-arc-worker'],
            'synthetic-private-worker-link',
          );
          expect(request.headers.containsKey('x-arc-session'), isFalse);
          if (request.method == 'POST') {
            if (request.url.path.endsWith('/accept')) {
              status = 'in_progress';
            } else {
              expect(request.url.path, '/work/tasks/job-a/submit');
              deliverable =
                  (jsonDecode(request.body) as Map)['content'] as String;
              status = 'submitted';
            }
            return http.Response('{}', 200);
          }
          expect(request.url.path, '/work/tasks');
          return http.Response(
            jsonEncode({
              'person': {'name': 'Alex', 'job_capacity': 2, 'active_jobs': 1},
              'groups': [
                {
                  'id': 'g',
                  'name': 'Research group',
                  'manager_name': 'Company CEO',
                },
              ],
              'tasks': [
                {
                  'id': 'job-a',
                  'title': 'Prepare customer interview findings',
                  'description': 'Submit three findings with supporting notes.',
                  'status': status,
                  'manager': 'ceo',
                  'result': deliverable,
                  'feedback': '',
                },
              ],
            }),
            200,
          );
        }),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          home: HumanWorkPortal(invitation: 'test', api: api),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('1 / 2 job slots'), findsOneWidget);
      expect(find.textContaining('Research group'), findsOneWidget);
      expect(find.text('Ask ARC'), findsNothing);
      expect(find.text('Send message'), findsNothing);
      await tester.ensureVisible(find.text('Accept job'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Accept job'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField),
        'Three findings and the supporting interview notes.',
      );
      await tester.ensureVisible(find.text('Submit work to manager'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Submit work to manager'));
      await tester.pumpAndSettle();
      expect(status, 'submitted');
      expect(deliverable, 'Three findings and the supporting interview notes.');
      expect(find.textContaining('Your manager’s review'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets(
    'company work starts only with explicit local autonomy and a selected model',
    (tester) async {
      bool enabled = false;
      final api = WorkApi(
        client: MockClient((request) async {
          if (request.method == 'PUT') {
            final body = jsonDecode(request.body) as Map;
            expect(body['confirm_local_autonomy'], isTrue);
            expect(body['model'], 'vendor/test:free');
            enabled = body['enabled'] as bool;
            return http.Response('{}', 200);
          }
          return http.Response(
            jsonEncode({
              'enabled': enabled,
              'model': 'vendor/test:free',
              'models': [
                {
                  'model_id': 'vendor/test:free',
                  'name': 'Test free model',
                  'input_price_per_million': 0,
                  'output_price_per_million': 0,
                },
              ],
              'tasks': [],
              'employees': [],
            }),
            200,
          );
        }),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          home: WorkBoard(sessionId: 'project', api: api),
        ),
      );
      await tester.pumpAndSettle();
      final start = find.widgetWithText(FilledButton, 'Start company work');
      expect(tester.widget<FilledButton>(start).onPressed, isNull);
      await tester.ensureVisible(
        find.text('Allow automatic local project work'),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Allow automatic local project work'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(start);
      await tester.pumpAndSettle();
      await tester.tap(start);
      await tester.pumpAndSettle();
      expect(enabled, isTrue);
      expect(find.text('Scheduler is running'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets(
    'paid models require pricing consent and keep the selected model during refresh',
    (tester) async {
      bool enabled = false;
      int starts = 0;
      final api = WorkApi(
        client: MockClient((request) async {
          if (request.method == 'PUT') {
            final body = jsonDecode(request.body) as Map;
            expect(body['confirm_local_autonomy'], isTrue);
            expect(body['confirm_paid_model'], isTrue);
            expect(body['model'], 'vendor/paid');
            enabled = body['enabled'] as bool;
            starts++;
            return http.Response('{}', 200);
          }
          return http.Response(
            jsonEncode({
              'enabled': enabled,
              'model': enabled ? 'vendor/paid' : 'vendor/test:free',
              'models': [
                {
                  'model_id': 'vendor/test:free',
                  'name': 'Test free model',
                  'input_price_per_million': 0,
                  'output_price_per_million': 0,
                },
                {
                  'model_id': 'vendor/paid',
                  'name': 'Test paid model',
                  'input_price_per_million': 1,
                  'output_price_per_million': 4,
                },
              ],
              'tasks': [],
              'employees': [],
            }),
            200,
          );
        }),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          home: WorkBoard(sessionId: 'project', api: api),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Test paid model').last);
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      expect(find.text('Test paid model'), findsOneWidget);
      final start = find.widgetWithText(FilledButton, 'Start company work');
      await tester.ensureVisible(
        find.text('Allow automatic local project work'),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Allow automatic local project work'));
      await tester.pumpAndSettle();
      expect(tester.widget<FilledButton>(start).onPressed, isNull);
      expect(starts, 0);
      await tester.ensureVisible(
        find.text('I agree to this model’s usage charges'),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('I agree to this model’s usage charges'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(start);
      await tester.pumpAndSettle();
      await tester.tap(start);
      await tester.pumpAndSettle();
      expect(starts, 1);
      expect(find.text('Scheduler is running'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('saving the planning model does not start the scheduler', (
    tester,
  ) async {
    bool saved = false;
    final api = WorkApi(
      client: MockClient((request) async {
        if (request.method == 'PUT') {
          final body = jsonDecode(request.body) as Map;
          expect(body['enabled'], isFalse);
          expect(body['confirm_local_autonomy'], isFalse);
          expect(body['model'], 'vendor/test:free');
          saved = true;
          return http.Response('{}', 200);
        }
        return http.Response(
          jsonEncode({
            'enabled': false,
            'model': 'vendor/test:free',
            'models': [
              {
                'model_id': 'vendor/test:free',
                'name': 'Test model',
                'input_price_per_million': 0,
                'output_price_per_million': 0,
              },
            ],
            'tasks': [],
            'employees': [],
          }),
          200,
        );
      }),
    );
    addTearDown(api.close);
    await tester.pumpWidget(
      MaterialApp(
        home: WorkBoard(sessionId: 'project', api: api),
      ),
    );
    await tester.pumpAndSettle();
    final save = find.widgetWithText(OutlinedButton, 'Save model choice');
    await tester.scrollUntilVisible(
      save,
      150,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(saved, isTrue);
    expect(find.text('Scheduler is paused'), findsOneWidget);
    expect(find.text('Pause company work'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
    'work board creates a verifiable task without requiring agent chat',
    (tester) async {
      Map? task;
      final api = WorkApi(
        client: MockClient((request) async {
          if (request.method == 'POST') {
            task = jsonDecode(request.body) as Map;
            return http.Response('{}', 201);
          }
          return http.Response(
            '{"enabled":false,"models":[],"tasks":[],"employees":[]}',
            200,
          );
        }),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          home: WorkBoard(sessionId: 'project', api: api),
        ),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Add work'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add work'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextField, 'What needs doing?'),
        'Fix discount bug',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Brief and acceptance criteria'),
        'Correct the discount and run the existing tests.',
      );
      await tester.tap(find.text('Require a passing terminal check'));
      await tester.tap(find.text('Add task'));
      await tester.pumpAndSettle();
      expect(task?['requires_check'], isTrue);
      expect(task?['assignee'], 'ceo');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
