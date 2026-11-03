import 'package:arc/frontend/arc_sidebar.dart';
import 'package:arc/frontend/chatsession.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets(
    'sidebar searches recent conversations and keeps options reachable on a narrow phone',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 740);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      String? optionsFor;
      var newChat = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ArcSidebar(
              sessions: [
                ChatSession(title: 'Launch plan', id: 'launch'),
                ChatSession(title: 'Marketing brief', id: 'marketing'),
              ],
              activeSessionId: 'launch',
              onNewChat: () => newChat = true,
              onCompany: () {},
              onMarketplace: () {},
              onPlugins: () {},
              onSettings: () {},
              onClose: () {},
              onOpenSession: (_) {},
              onSessionActions: (session) => optionsFor = session.id,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'launch');
      await tester.pumpAndSettle();
      expect(find.text('Launch plan'), findsOneWidget);
      expect(find.text('Marketing brief'), findsNothing);
      await tester.ensureVisible(
        find.byTooltip('Chat options for Launch plan'),
      );
      await tester.tap(find.byTooltip('Chat options for Launch plan'));
      expect(optionsFor, 'launch');
      await tester.tap(find.byTooltip('Clear conversation search'));
      await tester.pumpAndSettle();
      expect(find.text('Marketing brief'), findsOneWidget);
      await tester.ensureVisible(find.text('New conversation'));
      await tester.tap(find.text('New conversation'));
      expect(newChat, isTrue);
      expect(find.text('Workspace settings'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
