import 'package:arc/workspace_identity.dart';
import 'package:arc/workspace_storage.dart' as storage;

class ApiConfig {
  static final _identity = WorkspaceIdentity(
    read: storage.readWorkspace,
    write: storage.writeWorkspace,
  );
  static String get sessionToken => _identity.sessionToken;
  static String get companySessionId => _identity.company;
  static set companySessionId(String value) => _identity.company = value;
  static bool get remembersWorkspace => _identity.remembered;
  static Map<String, String> headers() => {'X-Arc-Session': sessionToken};
  static void resetSession() => _identity.reset();

  static const String _configuredBaseUrl = String.fromEnvironment(
    'ARC_API_BASE_URL',
  );

  static String get baseUrl {
    final configured = _configuredBaseUrl.trim();
    if (configured.isNotEmpty) {
      final resolved = Uri.base.resolve(configured).toString();
      return resolved.endsWith('/')
          ? resolved.substring(0, resolved.length - 1)
          : resolved;
    }

    return 'https://arc1-backend.nicesmoke-c99e1085.spaincentral.azurecontainerapps.io';
  }

  static Uri endpoint(String path, [Map<String, String>? queryParameters]) {
    return Uri.parse('$baseUrl$path').replace(queryParameters: queryParameters);
  }
}
