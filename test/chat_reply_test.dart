import 'package:arc/frontend/chat_reply.dart';
import 'package:arc/frontend/chatmessage.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const example = '''## Your student calculator

A simple plan with **clear choices**.

1. **Calculator type:** scientific or everyday math.
2. **Target user:** students.

| Detail | Choice |
| --- | --- |
| Audience | Students |
| First version | Basic calculations |

> Next step: choose your calculator type.

```python
print("a long example that stays inside its scrollable code block without breaking the phone layout")
```

![Example image](https://untrusted.example/tracker.png)
''';

void main() {
  testWidgets(
    'reply renders emphasis, lists and tables without raw formatting',
    (tester) async {
      tester.view.physicalSize = const Size(390, 1100);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ChatMessageView(
                message: Chatmessage(text: example, isAI: true),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final rendered = tester
          .widgetList<RichText>(find.byType(RichText))
          .map((w) => w.text.toPlainText())
          .join('\n');
      expect(rendered, contains('Your student calculator'));
      expect(rendered, contains('Calculator type:'));
      expect(rendered, isNot(contains('**')));
      expect(rendered, isNot(contains('| --- |')));
      expect(find.byType(Table), findsOneWidget);
      expect(find.byType(Image), findsNothing);
      expect(find.byType(SelectionArea), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('user text stays literal and a long reply fits a narrow screen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 740);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ListView(
            children: [
              ChatMessageView(
                message: Chatmessage(
                  text: '**my literal message**',
                  isMe: true,
                ),
              ),
              ChatMessageView(message: Chatmessage(text: example, isAI: true)),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('**my literal message**'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -450));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  test('reply links cannot launch script, file or credential URLs', () {
    for (final value in [
      'javascript:alert(1)',
      'file:///private.txt',
      'data:text/html,test',
      'https://user:password@example.com/',
    ]) {
      expect(replyLink(value), isNull);
    }
    expect(replyLink('https://example.com/guide')?.host, 'example.com');
  });
}
