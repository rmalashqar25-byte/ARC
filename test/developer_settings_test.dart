import 'dart:convert';
import 'package:arc/frontend/pages/developer_settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    'developer can choose OpenAI and save an owned key without restoring it to the form',
    (tester) async {
      Map<String, dynamic>? submitted;
      final client = MockClient((request) async {
        if (request.method == 'POST') {
          expect(request.url.path, '/developer/models');
          expect(jsonDecode(request.body)['model'], '');
          return http.Response(
            jsonEncode({
              'models': [
                {'id': 'vendor/chosen-model', 'name': 'Friendly Model Name'},
              ],
            }),
            200,
          );
        }
        if (request.method == 'PUT') {
          submitted = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'connection': {
                'provider': 'openai',
                'model': submitted!['model'],
              },
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode({'connection': {}, 'local_available': true}),
          200,
        );
      });
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: DeveloperSettingsPage(client: client),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('OpenRouter'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('OpenAI API').last);
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, 'API key'),
        'synthetic-test-key',
      );
      tester.testTextInput.hide();
      await tester.pumpAndSettle();
      expect(
        find.widgetWithText(TextFormField, 'Exact model ID'),
        findsNothing,
      );
      final load = find.text('Load available models');
      await tester.ensureVisible(load);
      await tester.pumpAndSettle();
      await tester.tap(load);
      await tester.pumpAndSettle();
      final choose = find.text('Choose a model');
      await tester.ensureVisible(choose);
      await tester.pumpAndSettle();
      await tester.tap(choose);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Friendly Model Name'));
      await tester.pumpAndSettle();
      final consent = find.text(
        'Use my provider account and its usage pricing',
      );
      await tester.ensureVisible(consent);
      await tester.pumpAndSettle();
      await tester.tap(consent);
      final save = find.text('Save my connection');
      await tester.ensureVisible(save);
      await tester.pumpAndSettle();
      await tester.tap(save);
      await tester.pumpAndSettle();
      expect(submitted!['provider'], 'openai');
      expect(submitted!['model'], 'vendor/chosen-model');
      expect(submitted!['api_key'], 'synthetic-test-key');
      expect(submitted!['confirm_usage'], true);
      expect(find.textContaining('Connection saved.'), findsOneWidget);
      expect(find.text('synthetic-test-key'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('local Ollama hides key entry and works on a narrow screen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient(
      (_) async => http.Response(
        jsonEncode({
          'local_available': true,
          'connection': {
            'provider': 'ollama',
            'model': 'llama-local',
            'supports_tools': true,
            'local': true,
          },
        }),
        200,
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: DeveloperSettingsPage(client: client),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextFormField, 'API key'), findsNothing);
    expect(
      find.text('Use my provider account and its usage pricing'),
      findsNothing,
    );
    expect(find.textContaining('localhost:11434'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
