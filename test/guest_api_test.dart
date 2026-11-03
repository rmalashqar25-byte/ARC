import 'dart:convert';
import 'package:arc/api_config.dart';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/pages/workspace_settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('agent API works without a login or token provider', () async {
    final token = ApiConfig.sessionToken;
    expect(
      token,
      matches(
        RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        ),
      ),
    );
    final api = CompanyApiClient(
      client: MockClient((request) async {
        expect(request.headers['x-arc-session'], token);
        expect(request.headers.containsKey('authorization'), isFalse);
        if (request.method == 'GET') return http.Response('{"agents":[]}', 200);
        expect(jsonDecode(request.body)['prompt'], 'Hello');
        return http.Response('{"message":"Hello guest"}', 200);
      }),
    );
    expect((await api.loadCatalog()).agents, isEmpty);
    expect(
      (await api.runCeo(prompt: 'Hello', sessionId: 'chat')).message,
      'Hello guest',
    );
  });

  test('reset replaces the shared workspace identity', () {
    final oldToken = ApiConfig.sessionToken;
    ApiConfig.resetSession();
    expect(ApiConfig.sessionToken, isNot(oldToken));
    expect(ApiConfig.headers()['X-Arc-Session'], ApiConfig.sessionToken);
  });

  testWidgets('workspace settings open without account controls', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: WorkspaceSettingsPage()));
    expect(find.text('Workspace settings'), findsOneWidget);
    expect(find.text('Guest'), findsNothing);
    expect(
      find.text('Workspace access lasts until this app closes.'),
      findsOneWidget,
    );
    await tester.scrollUntilVisible(find.text('Reset session'), 300);
    expect(find.text('Reset session'), findsOneWidget);
    expect(find.text('Log out'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
