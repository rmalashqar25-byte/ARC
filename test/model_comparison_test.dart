import 'dart:convert';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/project_team_market.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    'search, compare specific versions, and filter reasoning support',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1280, 1200);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final models = [
        for (var i = 1; i <= 2; i++)
          {
            'id': 'test/model-v$i',
            'model_id': 'test/model-v$i',
            'name': 'Model Version $i',
            'provider': 'test',
            'summary': 'Text model with a documented context window.',
            'role_id': 'cto',
            'role': 'Technology',
            'categories': ['it'],
            'supports_tools': true,
            'supports_reasoning': i == 1,
            'agent_compatible': true,
            'configured': true,
            'context_length': i * 65536,
            'input_modalities': ['text'],
            'output_modalities': ['text'],
            'input_price_per_million': i,
            'output_price_per_million': i * 3,
          },
      ];
      final api = CompanyApiClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode(
              request.url.path == '/company/marketplace'
                  ? {'agents': models}
                  : {'mode': 'undecided', 'members': []},
            ),
            200,
          ),
        ),
      );
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ProjectTeamMarket(
                api: api,
                sessionId: 'project-a',
                roles: const [],
                department: 'it',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Version 2');
      await tester.pumpAndSettle();
      expect(find.text('Model Version 1'), findsNothing);
      expect(find.text('Model Version 2'), findsOneWidget);
      await tester.enterText(find.byType(TextField), '');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Compare').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Compare'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Compare (2/3)'));
      await tester.pumpAndSettle();
      expect(find.byType(DataTable), findsOneWidget);
      expect(find.text('65536 tokens'), findsOneWidget);
      expect(find.text('131072 tokens'), findsOneWidget);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Reasoning'));
      await tester.pumpAndSettle();
      expect(find.text('Model Version 1'), findsOneWidget);
      expect(find.text('Model Version 2'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
