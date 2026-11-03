import 'dart:convert';
import 'package:uuid/uuid.dart';

/// Browser workspace access only. Provider credentials never belong here.
class WorkspaceIdentity {
  WorkspaceIdentity({
    required String? Function() read,
    required bool Function(String) write,
  }) : _write = write {
    try {
      final saved = jsonDecode(read() ?? '') as Map<String, dynamic>;
      if (saved['version'] == 1 &&
          _valid(saved['session']) &&
          _valid(saved['company'])) {
        sessionToken = saved['session'] as String;
        _company = saved['company'] as String;
      }
    } catch (_) {
      // Blocked storage or an invalid record must not prevent app entry.
    }
    _save();
  }

  final bool Function(String) _write;
  String sessionToken = const Uuid().v4();
  String _company = const Uuid().v4();
  bool remembered = false;

  static bool _valid(Object? value) =>
      value is String &&
      RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      ).hasMatch(value);

  String get company => _company;
  set company(String value) {
    if (!_valid(value)) throw ArgumentError('Invalid company identifier');
    _company = value;
    _save();
  }

  void reset() {
    sessionToken = const Uuid().v4();
    _company = const Uuid().v4();
    _save();
  }

  void _save() {
    try {
      remembered = _write(
        jsonEncode({
          'version': 1,
          'session': sessionToken,
          'company': _company,
        }),
      );
    } catch (_) {
      remembered = false;
    }
  }
}
