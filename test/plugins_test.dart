import 'dart:convert';

import 'package:arc/frontend/pages/plugins.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('offline terminal explains why its action is unavailable', (
    tester,
  ) async {
    final client = MockClient(
      (_) async => http.Response(
        jsonEncode({
          'plugins': [
            {
              'id': 'terminal_run',
              'display_name': 'Terminal Run',
              'description': 'Run local project checks.',
              'risk': 'approval_required',
              'install_kind': 'local_terminal',
              'installed': false,
              'ready': false,
              'available': false,
              'connection_state': 'offline',
              'connection_hint':
                  'Start the local terminal on this computer, then refresh.',
            },
          ],
        }),
        200,
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Plugins(
          client: client,
          accessTokenProvider: () async => 'test-session',
          devicePermissionProvider: () async => false,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Offline'), findsOneWidget);
    expect(
      find.text('Start the local terminal on this computer, then refresh.'),
      findsOneWidget,
    );
    expect(find.text('Not connected'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
    'local terminal is ready only after its workspace connection succeeds',
    (tester) async {
      var connected = false;
      final client = MockClient((request) async {
        expect(request.headers['x-arc-session'], 'terminal-session');
        if (request.method == 'POST') {
          expect(request.url.path, '/plugins/terminal/auto-connect');
          expect(jsonDecode(request.body), isEmpty);
          connected = true;
          return http.Response('{"connected":true}', 200);
        }
        return http.Response(
          jsonEncode({
            'plugins': [
              {
                'id': 'terminal_run',
                'display_name': 'Terminal Run',
                'description': 'Run approved project checks locally.',
                'risk': 'approval_required',
                'install_kind': 'local_terminal',
                'installed': connected,
                'ready': connected,
                'available': true,
              },
            ],
          }),
          200,
        );
      });
      await tester.pumpWidget(
        MaterialApp(
          home: Plugins(
            client: client,
            accessTokenProvider: () async => 'terminal-session',
            devicePermissionProvider: () async => false,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Not connected'), findsOneWidget);
      await tester.tap(find.text('Turn on'));
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsNothing);
      expect(connected, isTrue);
      expect(find.text('Ready'), findsOneWidget);
      expect(find.text('Connected'), findsOneWidget);
      expect(find.text('Turn on'), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('plugin catalog shows truthful installation states', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1100, 900);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    Uri? launched;
    final client = MockClient((request) async {
      expect(request.headers['x-arc-session'], 'test-token');
      if (request.url.path == '/github/connect') {
        return http.Response(
          jsonEncode({
            'authorization_url':
                'https://github.com/login/oauth/authorize?client_id=demo',
            'installation_url': 'https://github.com/apps/arc/installations/new',
          }),
          200,
        );
      }
      expect(request.url.path, '/plugins/catalog');
      return http.Response(
        jsonEncode({
          'plugins': [
            {
              'id': 'calculator',
              'display_name': 'Calculator',
              'description': 'Perform deterministic calculations.',
              'risk': 'low',
              'install_kind': 'built_in',
              'installed': true,
              'ready': true,
            },
            {
              'id': 'github',
              'display_name': 'GitHub',
              'description': 'Publish approved repository changes.',
              'risk': 'external_write',
              'install_kind': 'github_app',
              'installed': false,
              'ready': false,
              'available': true,
              'connections': [],
            },
            {
              'id': 'finance_connector',
              'display_name': 'Finance Connector',
              'description': 'Connect a configured finance service.',
              'risk': 'external_write',
              'install_kind': 'managed_connector',
              'installed': false,
              'ready': false,
              'available': false,
            },
          ],
        }),
        200,
        headers: const {'content-type': 'application/json'},
      );
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Plugins(
          client: client,
          accessTokenProvider: () async => 'test-token',
          externalLauncher: (uri) async {
            launched = uri;
            return true;
          },
          devicePermissionProvider: () async => false,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Agent tools'), findsOneWidget);
    expect(find.text('Calculator'), findsOneWidget);
    expect(find.text('GitHub'), findsOneWidget);
    expect(find.text('Connect'), findsOneWidget);
    expect(find.text('Finance Connector'), findsOneWidget);
    expect(find.text('Not available yet'), findsOneWidget);
    expect(find.byIcon(Icons.calculate_outlined), findsOneWidget);
    expect(find.byIcon(Icons.code_rounded), findsOneWidget);
    expect(find.byIcon(Icons.account_balance_outlined), findsOneWidget);
    final calculator = find.byKey(const ValueKey('plugin-calculator'));
    final github = find.byKey(const ValueKey('plugin-github'));
    final finance = find.byKey(const ValueKey('plugin-finance_connector'));
    expect(tester.getTopLeft(calculator).dy, tester.getTopLeft(github).dy);
    expect(tester.getTopLeft(calculator).dy, tester.getTopLeft(finance).dy);
    expect(
      tester.getTopLeft(github).dx,
      greaterThan(tester.getTopRight(calculator).dx),
    );
    expect(tester.getSize(calculator).height, tester.getSize(github).height);

    tester.view.physicalSize = const Size(700, 900);
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(calculator).dy, tester.getTopLeft(github).dy);
    expect(
      tester.getTopLeft(finance).dy,
      greaterThan(tester.getBottomLeft(calculator).dy),
    );

    tester.view.physicalSize = const Size(390, 844);
    await tester.pumpAndSettle();
    expect(
      tester.getTopLeft(github).dy,
      greaterThan(tester.getBottomLeft(calculator).dy),
    );
    await tester.ensureVisible(find.text('Connect'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Connect GitHub'), findsOneWidget);
    await tester.tap(find.text('2. Authorize GitHub'));
    await tester.pump();
    expect(launched?.host, 'github.com');
    Navigator.of(tester.element(find.text('Connect GitHub'))).pop();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
