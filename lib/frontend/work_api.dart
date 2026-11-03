import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:arc/api_config.dart';

class WorkApi {
  WorkApi({http.Client? client, this.workerToken})
    : _client = client ?? http.Client(),
      _owns = client == null;
  final http.Client _client;
  final bool _owns;
  final String? workerToken;

  Future<Map<String, dynamic>> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
  }) async {
    final headers = <String, String>{
      if (workerToken != null)
        'X-Arc-Worker': workerToken!
      else
        ...ApiConfig.headers(),
      if (body != null) 'Content-Type': 'application/json',
    };
    final uri = ApiConfig.endpoint(path);
    final response =
        await (method == 'POST'
                ? _client.post(uri, headers: headers, body: jsonEncode(body))
                : method == 'PUT'
                ? _client.put(uri, headers: headers, body: jsonEncode(body))
                : method == 'DELETE'
                ? _client.delete(uri, headers: headers)
                : _client.get(uri, headers: headers))
            .timeout(const Duration(seconds: 25));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError(
        response.statusCode == 401
            ? 'This work invitation is invalid or expired.'
            : 'We couldn’t save that change. Refresh and try again.',
      );
    }
    return Map<String, dynamic>.from(jsonDecode(response.body) as Map);
  }

  void close() {
    if (_owns) _client.close();
  }
}
