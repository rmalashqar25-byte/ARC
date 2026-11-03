import 'package:arc/frontend/external_links.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'external API links cannot redirect users to arbitrary destinations',
    () {
      for (final url in [
        'javascript:alert(1)',
        'data:text/html,attack',
        'file:///etc/passwd',
        'http://github.com/login',
        'https://github.com.attacker.example/login',
        'https://github.com@attacker.example/login',
        'https://attacker@github.com/login',
        'https://github.com:444/login',
        '//github.com/login',
      ]) {
        expect(trustedExternalUri(url, 'github.com'), isNull, reason: url);
      }
      expect(
        trustedExternalUri(
          'https://github.com/login/oauth/authorize?client_id=demo',
          'github.com',
        ),
        isNotNull,
      );
      expect(
        trustedExternalUri(
          'https://openrouter.ai/provider/model',
          'openrouter.ai',
        ),
        isNotNull,
      );
    },
  );
}
