import 'package:arc/android_automation.dart';
import 'package:flutter/material.dart';

class AccessibilitySettingsPage extends StatefulWidget {
  const AccessibilitySettingsPage({super.key});

  @override
  State<AccessibilitySettingsPage> createState() =>
      _AccessibilitySettingsPageState();
}

class _AccessibilitySettingsPageState extends State<AccessibilitySettingsPage>
    with WidgetsBindingObserver {
  bool _enabled = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refresh();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
    final enabled = await AndroidAutomation.isEnabled();
    if (mounted) {
      setState(() {
        _enabled = enabled;
        _loading = false;
      });
    }
  }

  Future<void> _openAndroidSettings() async {
    await AndroidAutomation.openSettings();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Android app control'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: const Color(0xFF1E1E1E),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: const Color(0xFF373737)),
            ),
            child: Row(
              children: [
                Icon(
                  _enabled ? Icons.check_circle : Icons.pause_circle,
                  color: _enabled
                      ? const Color(0xFF35C58A)
                      : const Color(0xFFAAAAAA),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _loading
                        ? 'Checking service…'
                        : _enabled
                        ? 'ARC App Control is on'
                        : 'ARC App Control is off',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          const Text(
            'Android requires you to confirm Accessibility access in system settings. ARC cannot silently turn this permission on or off.',
            style: TextStyle(color: Color(0xFFBBBBBB), height: 1.45),
          ),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _openAndroidSettings,
              icon: Icon(_enabled ? Icons.toggle_off : Icons.toggle_on),
              label: Text(
                _enabled
                    ? 'Open Android settings to turn off'
                    : 'Open Android settings to turn on',
              ),
            ),
          ),
          const SizedBox(height: 12),
          TextButton.icon(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh status'),
          ),
        ],
      ),
    );
  }
}
