import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class AndroidAutomation {
  static const MethodChannel _channel = MethodChannel('arc/accessibility');

  static bool get isSupported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  static Future<bool> isEnabled() async {
    if (!isSupported) return false;
    return await _channel.invokeMethod<bool>('isAccessibilityEnabled') ?? false;
  }

  static Future<void> openSettings() async {
    if (!isSupported) return;
    await _channel.invokeMethod<bool>('openAccessibilitySettings');
  }

  static Future<Map<String, dynamic>> executeActions(
    List<Map<String, dynamic>> actions,
  ) async {
    if (!isSupported) {
      return const {
        'success': false,
        'message': 'Android app control is only available on Android.',
      };
    }

    final raw = await _channel.invokeMethod<Map<Object?, Object?>>(
      'executeActions',
      actions,
    );
    return raw?.map((key, value) => MapEntry(key.toString(), value)) ??
        const {'success': false, 'message': 'No result returned.'};
  }
}

class AgentReply {
  const AgentReply({required this.message, required this.deviceActions});

  final String message;
  final List<Map<String, dynamic>> deviceActions;

  factory AgentReply.fromJson(Object? value) {
    if (value is! Map) {
      return AgentReply(
        message: value?.toString() ?? '',
        deviceActions: const [],
      );
    }

    final rawActions = value['device_actions'];
    final actions = <Map<String, dynamic>>[];
    if (rawActions is List) {
      for (final action in rawActions) {
        if (action is Map) {
          actions.add(
            action.map((key, item) => MapEntry(key.toString(), item)),
          );
        }
      }
    }

    return AgentReply(
      message: value['message']?.toString() ?? '',
      deviceActions: actions,
    );
  }
}
