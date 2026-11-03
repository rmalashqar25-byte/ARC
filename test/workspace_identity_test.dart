import 'dart:convert';
import 'package:arc/workspace_identity.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uuid/uuid.dart';

void main() {
  test(
    'reopening restores access and the active company without provider keys',
    () {
      String? record;
      WorkspaceIdentity open() => WorkspaceIdentity(
        read: () => record,
        write: (value) {
          record = value;
          return true;
        },
      );
      final original = open();
      final company = const Uuid().v4();
      original.company = company;
      final restored = open();
      expect(restored.sessionToken, original.sessionToken);
      expect(restored.company, company);
      expect(restored.remembered, isTrue);
      expect((jsonDecode(record!) as Map).keys.toSet(), {
        'version',
        'session',
        'company',
      });
    },
  );

  test('reset replaces both saved identifiers for subsequent visits', () {
    String? record;
    WorkspaceIdentity open() => WorkspaceIdentity(
      read: () => record,
      write: (value) {
        record = value;
        return true;
      },
    );
    final identity = open();
    final token = identity.sessionToken, company = identity.company;
    identity.reset();
    final restored = open();
    expect(restored.sessionToken, isNot(token));
    expect(restored.company, isNot(company));
    expect(restored.sessionToken, identity.sessionToken);
  });

  test('blocked browser storage leaves a usable temporary workspace', () {
    final identity = WorkspaceIdentity(
      read: () => throw StateError('Blocked'),
      write: (_) => throw StateError('Blocked'),
    );
    expect(identity.remembered, isFalse);
    expect(identity.sessionToken, hasLength(36));
    expect(identity.reset, returnsNormally);
  });

  test('invalid and unsupported records cannot select another workspace', () {
    for (final record in [
      'invalid',
      '[]',
      '{}',
      jsonEncode({
        'version': 2,
        'session': const Uuid().v4(),
        'company': const Uuid().v4(),
      }),
      jsonEncode({'version': 1, 'session': '../other', 'company': 'anything'}),
    ]) {
      String? saved;
      final identity = WorkspaceIdentity(
        read: () => record,
        write: (value) {
          saved = value;
          return true;
        },
      );
      expect(identity.sessionToken, hasLength(36));
      expect(jsonDecode(saved!)['version'], 1);
    }
  });
}
