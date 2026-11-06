import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:arc/frontend/pages/ai_page.dart';
import 'package:flutter/material.dart';
import 'package:arc/frontend/pages/human_work_portal.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  LicenseRegistry.addLicense(() async* {
    yield LicenseEntryWithLineBreaks([
      'ARC',
    ], await rootBundle.loadString('assets/legal/ARC-LICENSE.txt'));
  });
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'ARC',
    debugShowCheckedModeBanner: false,
    theme: ThemeData.dark(useMaterial3: true).copyWith(
      colorScheme: const ColorScheme.dark(
        primary: Colors.white,
        onPrimary: Colors.black,
        secondary: Colors.white,
        surface: Color(0xFF191919),
      ),
      scaffoldBackgroundColor: Colors.black,
    ),
    home: Uri.base.queryParameters['view'] == 'work'
        ? HumanWorkPortal(
            invitation: Uri.splitQueryString(Uri.base.fragment)['invite'] ?? '',
          )
        : const AiPage(),
  );
}
