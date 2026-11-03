import 'dart:async';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/company_live_activity.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class ActivityPreviewApi extends CompanyApiClient {
  ActivityPreviewApi({
    this.offline = false,
    this.groups = const [],
    this.events = const [],
  });
  bool offline;
  List<CompanyGroup> groups;
  List<CompanyEvent> events;
  final updates = StreamController<CompanyEvent>.broadcast();
  @override
  Future<List<CompanyGroup>> loadGroups(String sessionId) async {
    if (offline) throw const CompanyApiException('Network unavailable');
    return groups;
  }

  @override
  Future<CompanyEventsPage> loadEvents(
    String sessionId, {
    int afterId = 0,
    int limit = 200,
  }) async {
    if (offline) throw const CompanyApiException('Network unavailable');
    return CompanyEventsPage(
      events: events,
      nextAfterId: events.isEmpty ? 0 : events.last.id,
    );
  }

  @override
  Stream<CompanyEvent> watchEvents(String sessionId, {int afterId = 0}) =>
      updates.stream;
}

CompanyEvent activityPreviewEvent(int id, String content, {String? groupId}) =>
    CompanyEvent(
      id: id,
      sessionId: 'project',
      groupId: groupId,
      senderId: 'ceo',
      recipientId: 'cto',
      type: 'task_delegated',
      content: content,
      metadata: const {},
      createdAt: DateTime.utc(2026, 10, 22, 10, id),
    );

class ActivitySessionRaceApi extends ActivityPreviewApi {
  final oldRequest = Completer<CompanyEventsPage>();
  @override
  Future<CompanyEventsPage> loadEvents(
    String sessionId, {
    int afterId = 0,
    int limit = 200,
  }) {
    if (sessionId == 'old') return oldRequest.future;
    return Future.value(
      CompanyEventsPage(
        events: [activityPreviewEvent(2, 'Current project update')],
        nextAfterId: 2,
      ),
    );
  }
}

void main() {
  testWidgets(
    'offline recovery preserves updates and includes events before their room loads',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(370, 760);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final api = ActivityPreviewApi(offline: true);
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: CompanyLiveActivity(api: api, sessionId: 'project'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Offline'), findsOneWidget);
      expect(find.text('Retry connection'), findsOneWidget);
      api.offline = false;
      await tester.tap(find.text('Retry connection'));
      await tester.pumpAndSettle();
      expect(find.text('Ready'), findsOneWidget);
      api.updates.add(
        activityPreviewEvent(
          1,
          'Design the first prototype',
          groupId: 'not-loaded-yet',
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Live'), findsOneWidget);
      expect(find.text('Design the first prototype'), findsOneWidget);
      api.updates.addError(Exception('Provider implementation details'));
      await tester.pumpAndSettle();
      expect(find.text('Reconnecting'), findsOneWidget);
      expect(find.text('Design the first prototype'), findsOneWidget);
      expect(
        find.textContaining('Provider implementation details'),
        findsNothing,
      );
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await api.updates.close();
      api.close();
    },
  );

  testWidgets('room filtering and close action fit a narrow phone', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 700);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    final api = ActivityPreviewApi(
      groups: const [
        CompanyGroup(
          id: 'research',
          name: 'Research room',
          directorId: 'marketing',
          objective: 'Review evidence',
          status: 'active',
          members: [],
        ),
        CompanyGroup(
          id: 'engineering',
          name: 'Engineering room',
          directorId: 'cto',
          objective: 'Build',
          status: 'active',
          members: [],
        ),
      ],
      events: [
        activityPreviewEvent(
          1,
          'Review customer research',
          groupId: 'research',
        ),
        activityPreviewEvent(2, 'Build the prototype', groupId: 'engineering'),
      ],
    );
    var closed = false;
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: CompanyLiveActivity(
            api: api,
            sessionId: 'project',
            onClose: () => closed = true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ChoiceChip, 'Research room'));
    await tester.pumpAndSettle();
    expect(find.text('Review customer research'), findsOneWidget);
    expect(find.text('Build the prototype'), findsNothing);
    await tester.tap(find.widgetWithText(ChoiceChip, 'All updates'));
    await tester.pumpAndSettle();
    expect(find.text('Build the prototype'), findsOneWidget);
    await tester.tap(find.byTooltip('Close activity'));
    expect(closed, isTrue);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await api.updates.close();
    api.close();
  });
  testWidgets(
    'switching projects ignores a late response from the previous activity feed',
    (tester) async {
      final api = ActivitySessionRaceApi();
      Widget screen(String sessionId) => MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: CompanyLiveActivity(api: api, sessionId: sessionId),
        ),
      );
      await tester.pumpWidget(screen('old'));
      await tester.pump();
      await tester.pumpWidget(screen('new'));
      await tester.pumpAndSettle();
      expect(find.text('Current project update'), findsOneWidget);
      api.oldRequest.complete(
        CompanyEventsPage(
          events: [activityPreviewEvent(1, 'Previous project update')],
          nextAfterId: 1,
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Previous project update'), findsNothing);
      expect(find.text('Current project update'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await api.updates.close();
      api.close();
    },
  );
}
