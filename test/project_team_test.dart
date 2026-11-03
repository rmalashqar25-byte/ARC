import 'dart:convert';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/project_team_market.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    'hire a real model, restore its project role, and remove it on a phone',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 740);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      Map<String, dynamic> team = {'mode': 'undecided', 'members': []};
      final api = CompanyApiClient(
        client: MockClient((request) async {
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
          expect(request.url.path, '/company/sessions/project-a/team');
          if (request.method == 'PUT') {
            team = jsonDecode(request.body) as Map<String, dynamic>;
          }
          return http.Response(jsonEncode(team), 200);
        }),
      );
      addTearDown(api.close);
      Widget screen(Key key) => MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: ProjectTeamMarket(
              key: key,
              api: api,
              sessionId: 'project-a',
              roles: const [
                CompanyAgent(
                  id: 'cto',
                  name: 'CTO',
                  jobTitle: 'Chief Technology Officer',
                  department: 'IT',
                  purpose: 'Build',
                  provider: 'openrouter',
                  reportsTo: 'ceo',
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpWidget(screen(const ValueKey(1)));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Claude'));
      await tester.tap(find.text('Claude'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add to my project'));
      await tester.pumpAndSettle();
      expect(team['mode'], 'manual');
      expect(team['members'], [
        {'agent_id': 'claude', 'role_id': 'cto'},
      ]);
      expect(find.text('Claude · Chief Technology Officer'), findsOneWidget);
      await tester.pumpWidget(screen(const ValueKey(2)));
      await tester.pumpAndSettle();
      expect(find.text('Claude · Chief Technology Officer'), findsOneWidget);
      await tester.tap(
        find
            .descendant(of: find.byType(InputChip), matching: find.byType(Icon))
            .last,
      );
      await tester.pumpAndSettle();
      expect(team['members'], isEmpty);
      expect(tester.takeException(), isNull);
    },
  );
}
