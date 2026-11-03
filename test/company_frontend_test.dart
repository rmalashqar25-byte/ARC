import 'dart:convert';

import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/pages/companypage/company_ceo_workspace.dart';
import 'package:arc/frontend/pages/companypage/company_dashboard.dart';
import 'package:arc/frontend/pages/companypage/market.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _catalog = {
  'agents': [
    {
      'id': 'ceo',
      'name': 'Company CEO',
      'job_title': 'Chief Executive Officer',
      'department': 'Executive',
      'purpose': 'Set priorities and delegate company work.',
      'provider': 'google_ai_studio',
      'reports_to': null,
    },
    {
      'id': 'cto',
      'name': 'Chief Technology Officer',
      'job_title': 'CTO',
      'department': 'Technology',
      'purpose': 'Lead technology.',
      'provider': 'openrouter',
      'reports_to': 'ceo',
    },
    {
      'id': 'app_developer',
      'name': 'Application Developer',
      'job_title': 'Application Developer',
      'department': 'Technology',
      'purpose': 'Build applications.',
      'provider': 'openrouter',
      'reports_to': 'cto',
    },
  ],
};

const _group = {
  'group_id': 'group-1',
  'name': 'Technology group',
  'director_id': 'cto',
  'objective': 'Build the mobile application',
  'status': 'active',
  'members': [
    {'agent_id': 'ceo', 'membership_role': 'executive', 'added_by': 'system'},
    {'agent_id': 'cto', 'membership_role': 'director', 'added_by': 'ceo'},
    {
      'agent_id': 'app_developer',
      'membership_role': 'employee',
      'added_by': 'cto',
    },
  ],
};

void main() {
  testWidgets('sample human profile is clearly fictional and cannot be hired', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    final api = CompanyApiClient(
      client: MockClient((request) async {
        expect(request.method, 'GET');
        if (request.url.path == '/company/talent/profile') {
          return http.Response('{"profile":null}', 200);
        }
        expect(request.url.path, '/company/talent');
        return http.Response(
          jsonEncode({
            'profiles': [
              {
                'id': 'example-human-profile',
                'name': 'Maya Chen',
                'role': 'Research & product designer',
                'summary':
                    'Example: turns customer interviews into a product brief.',
                'skills': ['Customer research', 'Product design'],
                'department': 'general',
                'availability': 'unavailable',
                'pricing': 'hour',
                'rate': 25,
                'is_example': true,
                'is_mine': false,
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
        home: Market(
          api: api,
          sessionId: 'example-project',
          initialKind: 'human',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Example'), findsOneWidget);
    expect(find.textContaining('Example rate'), findsOneWidget);
    await tester.ensureVisible(find.text('Maya Chen'));
    await tester.tap(find.text('Maya Chen'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Maya is fictional'), findsOneWidget);
    expect(find.text('Prepare a project brief'), findsNothing);
    expect(
      find.widgetWithText(FilledButton, 'Add my employee'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('marketplace reveals agents only after choosing AI agents', (
    tester,
  ) async {
    var requests = 0;
    final api = CompanyApiClient(
      client: MockClient((request) async {
        requests++;
        if (request.url.path == '/company/catalog') {
          return http.Response(jsonEncode(_catalog), 200);
        }
        if (request.url.path == '/company/marketplace') {
          return http.Response(
            jsonEncode({
              'agents': [
                {
                  'id': 'claude',
                  'name': 'Claude',
                  'summary': 'Plans architecture and leads engineering.',
                  'role_id': 'cto',
                  'role': 'Chief Technology Officer',
                  'price': 59,
                  'model_env': 'ARC_MARKET_CLAUDE_MODEL',
                  'configured': true,
                },
              ],
            }),
            200,
          );
        }
        if (request.url.path.endsWith('/team')) {
          return http.Response(
            jsonEncode({'mode': 'undecided', 'members': []}),
            200,
          );
        }
        return http.Response('Not found', 404);
      }),
    );
    addTearDown(api.close);
    await tester.pumpWidget(
      MaterialApp(
        home: Market(api: api, sessionId: 'project-1'),
      ),
    );
    await tester.pumpAndSettle();
    expect(requests, 0);
    expect(find.text('Claude'), findsNothing);
    expect(find.text('Research'), findsOneWidget);
    await tester.tap(find.text('Research'));
    await tester.pumpAndSettle();
    expect(requests, 0);
    expect(find.text('AI models'), findsOneWidget);
    expect(find.text('Human talent'), findsOneWidget);
    expect(find.text('Your employees'), findsOneWidget);
    await tester.tap(find.text('AI models'));
    await tester.pumpAndSettle();
    expect(find.text('Claude'), findsOneWidget);
    await tester.tap(find.text('Explore'));
    await tester.pumpAndSettle();
    expect(find.text('Claude'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'human directory saves a private brief without contacting a person',
    (tester) async {
      var saved = false;
      final api = CompanyApiClient(
        client: MockClient((request) async {
          if (request.url.path == '/company/talent') {
            return http.Response(
              jsonEncode({
                'profiles': [
                  {
                    'id': 'person-1',
                    'name': 'Alex',
                    'role': 'Product designer',
                    'summary':
                        'I create thoughtful digital experiences for growing companies.',
                    'skills': ['Design', 'Flutter'],
                    'availability': 'available',
                    'pricing': 'hour',
                    'rate': 35,
                    'published': true,
                    'is_mine': false,
                  },
                ],
              }),
              200,
            );
          }
          if (request.url.path == '/company/talent/profile') {
            return http.Response(jsonEncode({'profile': null}), 200);
          }
          if (request.url.path == '/company/talent/person-1/briefs') {
            final body = jsonDecode(request.body) as Map;
            expect(body['session_id'], 'project-1');
            expect(body['description'], 'Design a homepage');
            saved = true;
            return http.Response(
              jsonEncode({'status': 'draft_assignment'}),
              201,
            );
          }
          fail('Unexpected request ${request.url.path}');
        }),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          home: Market(api: api, sessionId: 'project-1', initialKind: 'human'),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Alex'));
      await tester.tap(find.text('Alex'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Prepare a project brief'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'Design a homepage');
      await tester.tap(find.text('Save project brief'));
      await tester.pumpAndSettle();
      expect(saved, isTrue);
      expect(find.textContaining('No message was sent.'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pump(const Duration(milliseconds: 300));
    },
  );

  testWidgets('company dashboard loads the CEO and empty group state', (
    WidgetTester tester,
  ) async {
    final api = CompanyApiClient(
      accessTokenProvider: () async => 'test-token',
      client: MockClient((request) async {
        expect(request.headers['x-arc-session'], 'test-token');
        if (request.url.path == '/company/catalog') {
          return http.Response(jsonEncode(_catalog), 200);
        }
        if (request.url.path.endsWith('/groups')) {
          return http.Response(jsonEncode({'groups': []}), 200);
        }
        return http.Response('Not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: CompanyDashboard(api: api, initialSessionId: 'session-1'),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Your company'), findsOneWidget);
    expect(find.text('Explore team marketplace'), findsOneWidget);
    expect(find.text('Ask the CEO to start a project'), findsNothing);
    expect(find.text('No groups yet'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('CEO message renders backend-created group and events', (
    WidgetTester tester,
  ) async {
    final api = CompanyApiClient(
      accessTokenProvider: () async => 'test-token',
      client: MockClient((request) async {
        expect(request.headers['x-arc-session'], 'test-token');
        if (request.method == 'GET' && request.url.path.endsWith('/groups')) {
          return http.Response(jsonEncode({'groups': []}), 200);
        }
        if (request.method == 'GET' && request.url.path.endsWith('/events')) {
          return http.Response(
            jsonEncode({'events': [], 'next_after_id': 0}),
            200,
          );
        }
        if (request.method == 'POST' &&
            request.url.path == '/company/ceo/run') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['prompt'], 'Build my app');
          expect(body['session_id'], 'session-1');
          return http.Response(
            jsonEncode({
              'message': 'I created a Technology group led by the CTO.',
              'groups': [_group],
              'events': [
                {
                  'id': 1,
                  'session_id': 'session-1',
                  'group_id': null,
                  'sender_id': 'user',
                  'recipient_id': 'ceo',
                  'event_type': 'user_message',
                  'content': 'Build my app',
                  'metadata': {},
                  'created_at': 1,
                },
                {
                  'id': 2,
                  'session_id': 'session-1',
                  'group_id': 'group-1',
                  'sender_id': 'ceo',
                  'recipient_id': 'cto',
                  'event_type': 'group_created',
                  'content': 'Created Technology group.',
                  'metadata': {},
                  'created_at': 2,
                },
                {
                  'id': 3,
                  'session_id': 'session-1',
                  'group_id': null,
                  'sender_id': 'ceo',
                  'recipient_id': 'user',
                  'event_type': 'ceo_response',
                  'content': 'I created a Technology group led by the CTO.',
                  'metadata': {},
                  'created_at': 3,
                },
              ],
              'pending_approvals': [],
            }),
            200,
          );
        }
        return http.Response('Not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: CompanyCeoWorkspace(
          api: api,
          sessionId: 'session-1',
          initialCatalog: CompanyCatalog.fromJson(_catalog),
          enableLiveUpdates: false,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.enterText(find.byType(TextField), 'Build my app');
    await tester.tap(find.byIcon(Icons.arrow_upward));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.text('I created a Technology group led by the CTO.'),
      findsOneWidget,
    );

    await tester.tap(find.text('Groups'));
    await tester.pumpAndSettle();
    expect(find.text('Technology group'), findsOneWidget);
    expect(find.text('Application Developer'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('CEO workspace remains stable after phone rotation', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(412, 915);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    final api = CompanyApiClient(
      accessTokenProvider: () async => 'test-token',
      client: MockClient((request) async {
        if (request.url.path.endsWith('/groups')) {
          return http.Response(jsonEncode({'groups': []}), 200);
        }
        if (request.url.path.endsWith('/events')) {
          return http.Response(
            jsonEncode({'events': [], 'next_after_id': 0}),
            200,
          );
        }
        return http.Response('Not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: CompanyCeoWorkspace(
          api: api,
          sessionId: 'rotation-session',
          initialCatalog: CompanyCatalog.fromJson(_catalog),
          enableLiveUpdates: false,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.takeException(), isNull);

    tester.view.physicalSize = const Size(915, 412);
    await tester.pumpAndSettle();
    expect(find.text('Company CEO'), findsOneWidget);
    expect(find.text('No company groups yet'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
