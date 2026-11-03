// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:arc/frontend/pages/ai_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('main chat stays centered and shows activity only on request', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1920, 900);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(const MaterialApp(home: AiPage()));
    await tester.pump();
    expect(find.text('Company activity'), findsNothing);
    expect(find.byTooltip('Show live stream'), findsOneWidget);
    final composerCenter = tester
        .getCenter(find.byType(TextFormField).first)
        .dx;
    await tester.tap(find.byTooltip('Show live stream'));
    await tester.pump();
    expect(find.text('Company activity'), findsOneWidget);
    expect(
      tester.getCenter(find.byType(TextFormField).first).dx,
      closeTo((1920 - 370) / 2, 1),
    );
    expect(composerCenter, closeTo(960, 1));
    expect(
      tester.getSize(find.byType(TextFormField).first).height,
      lessThan(65),
    );
    await tester.tap(find.byTooltip('Hide live stream'));
    await tester.pump();
    expect(find.text('Company activity'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('AI page renders chat composer and app header', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: AiPage()));

    expect(find.text('Ask ARC'), findsOneWidget);
    expect(find.text('ARC'), findsOneWidget);
    expect(find.byIcon(Icons.edit_note), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('holding a recent chat opens rename and delete actions', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: AiPage()));

    await tester.enterText(find.byType(TextFormField), 'Project plan');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.sort));
    await tester.pumpAndSettle();

    Finder recentChat(String title) =>
        find.descendant(of: find.byType(Drawer), matching: find.text(title));

    await tester.ensureVisible(recentChat('Project plan'));
    await tester.longPress(recentChat('Project plan'));
    await tester.pumpAndSettle();
    expect(find.text('Rename'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);

    await tester.tap(find.text('Rename'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Launch plan');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(recentChat('Launch plan'), findsOneWidget);

    await tester.ensureVisible(recentChat('Launch plan'));
    await tester.longPress(recentChat('Launch plan'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(find.text('Delete chat?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('drawer opens workspace settings', (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: AiPage()));

    await tester.tap(find.byIcon(Icons.sort));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Workspace settings'));
    await tester.pumpAndSettle();

    expect(find.text('Workspace settings'), findsOneWidget);
    expect(find.text('Android app control'), findsNothing);
    expect(find.text('Approval'), findsOneWidget);
    await tester.tap(find.text('Approval'));
    await tester.pumpAndSettle();
    expect(find.text('Allow all tools'), findsOneWidget);
    await tester.tap(find.text('Ask before every tool').last);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Reset session'), 250);
    expect(find.text('Reset session'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
    'chat, drawer, and workspace settings layouts remain stable in landscape',
    (WidgetTester tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(915, 412);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(const MaterialApp(home: AiPage()));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.tap(find.byIcon(Icons.sort));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('Workspace settings'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Approval'), 180);
      await tester.pumpAndSettle();
      expect(find.text('Approval'), findsOneWidget);
      expect(tester.takeException(), isNull);

      tester.view.physicalSize = const Size(412, 915);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
