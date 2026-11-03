import 'package:arc/frontend/company_api_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('HTTP failures never expose server details to users', () async {
    for (final status in [400, 401, 403, 404, 409, 422, 429, 500, 502, 503]) {
      final api = CompanyApiClient(
        client: MockClient(
          (request) async => http.Response(
            '{"detail":"ClientException https://private.example ARC_API_KEY=SYNTHETIC_SECRET"}',
            status,
          ),
        ),
      );
      try {
        await api.runCeo(prompt: 'Test', sessionId: 'local');
        fail('Expected a failure');
      } on CompanyApiException catch (error) {
        expect(error.statusCode, status);
        for (final text in [
          'ClientException',
          'private.example',
          'ARC_API_KEY',
          'SYNTHETIC_SECRET',
        ]) {
          expect(error.message, isNot(contains(text)));
        }
      } finally {
        api.close();
      }
    }
  });
}
