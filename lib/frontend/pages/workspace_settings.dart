import 'package:arc/frontend/arc_design.dart';
import 'package:arc/frontend/pages/developer_settings.dart';
import 'package:arc/frontend/user_messages.dart';
import 'dart:convert';

import 'package:arc/api_config.dart';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/pages/ai_page.dart';
import 'package:flutter/material.dart';
import 'package:arc/frontend/work_api.dart';

class WorkspaceSettingsPage extends StatefulWidget {
  const WorkspaceSettingsPage({super.key, this.sessionId = '', this.api});

  final String sessionId;
  final CompanyApiClient? api;

  @override
  State<WorkspaceSettingsPage> createState() => _WorkspaceSettingsPageState();
}

class _WorkspaceSettingsPageState extends State<WorkspaceSettingsPage> {
  late final CompanyApiClient _api;
  late final bool _ownsApi;
  String _mode = 'ask';
  bool _loading = true;
  bool _saving = false;
  String? _error;
  List<Map<String, dynamic>> _requests = const [];

  @override
  void initState() {
    super.initState();
    _ownsApi = widget.api == null;
    _api = widget.api ?? CompanyApiClient();
    _load();
  }

  Future<void> _load() async {
    try {
      final mode = await _api.loadApprovalMode();
      final requests = await _api.loadApprovalRequests();
      if (mounted) {
        setState(() {
          _mode = mode;
          _requests = requests;
          _error = null;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = requestFailureMessage());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _setMode(String mode) async {
    if (_saving || mode == _mode) return;
    if (mode == 'allow') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Allow all agent tools?'),
          content: const Text(
            'Agents may use every tool available to their role without asking, including file changes, terminal, browser, cloud, and publishing actions. This applies while the current backend is running. Company work uses its own restricted local scope.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Allow all'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final saved = await _api.saveApprovalMode(mode);
      if (mounted) setState(() => _mode = saved);
    } catch (error) {
      if (mounted) setState(() => _error = requestFailureMessage());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _showApprovalChoices() async {
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: const Color(0xFF1A1A1A),
      builder: (sheetContext) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Approval',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 23,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'One choice for every agent tool in this temporary session.',
                style: TextStyle(color: Color(0xFFAAAAAA)),
              ),
              const SizedBox(height: 18),
              ListTile(
                leading: Icon(
                  _mode == 'ask'
                      ? Icons.check_circle
                      : Icons.radio_button_unchecked,
                  color: const Color(0xFFD0A7FF),
                ),
                title: const Text(
                  'Ask before every tool',
                  style: TextStyle(color: Colors.white),
                ),
                subtitle: const Text(
                  'Review each proposed action.',
                  style: TextStyle(color: Color(0xFFAAAAAA)),
                ),
                onTap: () {
                  Navigator.pop(sheetContext);
                  _setMode('ask');
                },
              ),
              ListTile(
                leading: Icon(
                  _mode == 'allow'
                      ? Icons.check_circle
                      : Icons.radio_button_unchecked,
                  color: const Color(0xFFD0A7FF),
                ),
                title: const Text(
                  'Allow all tools',
                  style: TextStyle(color: Colors.white),
                ),
                subtitle: const Text(
                  'Agents can use available tools automatically.',
                  style: TextStyle(color: Color(0xFFAAAAAA)),
                ),
                onTap: () {
                  Navigator.pop(sheetContext);
                  _setMode('allow');
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _decide(Map<String, dynamic> request, bool approve) async {
    if (_saving) return;
    if (approve) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text('Approve ${request['tool']}?'),
          content: Text(
            const JsonEncoder.withIndent('  ').convert(request['arguments']),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Approve action'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await _api.decideApprovalRequest(
        id: request['approval_id'].toString(),
        sessionId: request['session_id'].toString(),
        approve: approve,
      );
      if (mounted) {
        setState(
          () => _requests = _requests
              .where((item) => item['approval_id'] != request['approval_id'])
              .toList(),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = requestFailureMessage());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    if (_ownsApi) _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: arcCanvas,
    appBar: AppBar(
      title: const Text('Workspace settings'),
      backgroundColor: arcCanvas,
      foregroundColor: Colors.white,
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 26, 24, 32),
          children: [
            const Align(
              alignment: Alignment.centerLeft,
              child: ArcOrbit(size: 74),
            ),
            const SizedBox(height: 14),
            const Text(
              'YOUR SPACE',
              style: TextStyle(
                color: arcLime,
                fontSize: 11,
                letterSpacing: 2.5,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Make ARC yours.',
              style: TextStyle(
                color: Colors.white,
                fontSize: 38,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              ApiConfig.remembersWorkspace
                  ? 'Workspace access is saved on this browser.'
                  : 'Workspace access lasts until this app closes.',
              style: const TextStyle(color: Color(0xFF9CA8B9)),
            ),
            const SizedBox(height: 24),
            _SettingsCard(
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const _SettingsIcon(Icons.tune_rounded, arcLime),
                title: const Text(
                  'Developer connections',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                subtitle: const Text(
                  'Your own API keys, Ollama, and custom models',
                  style: TextStyle(color: Color(0xFFAAAAAA)),
                ),
                trailing: const Icon(
                  Icons.chevron_right,
                  color: Colors.white70,
                ),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => const DeveloperSettingsPage(),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 14),
            _SettingsCard(
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const _SettingsIcon(
                  Icons.verified_user_outlined,
                  arcLilac,
                ),
                title: const Text(
                  'Approval',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                subtitle: Text(
                  _loading
                      ? 'Loading…'
                      : _mode == 'allow'
                      ? 'Allow all tools'
                      : 'Ask before every tool',
                  style: const TextStyle(color: Color(0xFFAAAAAA)),
                ),
                trailing: const Icon(
                  Icons.chevron_right,
                  color: Colors.white70,
                ),
                onTap: _loading || _saving ? null : _showApprovalChoices,
              ),
            ),
            if (_saving) const LinearProgressIndicator(color: Colors.white),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  _error!,
                  style: const TextStyle(color: Colors.redAccent),
                ),
              ),
            const SizedBox(height: 14),
            _SettingsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Pending actions',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 19,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      IconButton(
                        tooltip: 'Refresh approvals',
                        onPressed: _loading ? null : _load,
                        icon: const Icon(Icons.refresh, color: Colors.white),
                      ),
                    ],
                  ),
                  if (_requests.isEmpty)
                    const Text(
                      'All clear. Your team has what it needs.',
                      style: TextStyle(color: Color(0xFF9CA8B9)),
                    ),
                  for (final request in _requests)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${request['role']} · ${request['tool']}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          Text(
                            const JsonEncoder.withIndent(
                              '  ',
                            ).convert(request['arguments']),
                            maxLines: 4,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Color(0xFF9CA8B9),
                              fontSize: 12,
                            ),
                          ),
                          Wrap(
                            spacing: 8,
                            children: [
                              OutlinedButton(
                                onPressed: _saving
                                    ? null
                                    : () => _decide(request, false),
                                child: const Text('Deny'),
                              ),
                              FilledButton(
                                onPressed: _saving
                                    ? null
                                    : () => _decide(request, true),
                                child: const Text('Approve'),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 28),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.redAccent,
                side: const BorderSide(color: Color(0xFF59413F)),
                minimumSize: const Size.fromHeight(52),
              ),
              onPressed: _saving
                  ? null
                  : () async {
                      final work = WorkApi();
                      try {
                        await work.request(
                          '/company/work/pause-all',
                          method: 'POST',
                          body: {},
                        );
                      } catch (_) {
                        work.close();
                        if (mounted) {
                          setState(
                            () => _error =
                                'Reconnect to company work before resetting. Your current access has been kept.',
                          );
                        }
                        return;
                      }
                      work.close();
                      if (!context.mounted) return;
                      ApiConfig.resetSession();
                      Navigator.of(context).pushAndRemoveUntil(
                        MaterialPageRoute(builder: (_) => const AiPage()),
                        (_) => false,
                      );
                    },
              icon: const Icon(Icons.restart_alt_rounded),
              label: const Text('Reset session'),
            ),
          ],
        ),
      ),
    ),
  );
}

class _SettingsCard extends StatelessWidget {
  const _SettingsCard({required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Material(
    color: arcPanel,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(22),
      side: const BorderSide(color: Color(0xFF303A31)),
    ),
    child: Padding(padding: const EdgeInsets.all(20), child: child),
  );
}

class _SettingsIcon extends StatelessWidget {
  const _SettingsIcon(this.icon, this.color);
  final IconData icon;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
    width: 48,
    height: 48,
    decoration: BoxDecoration(
      color: color.withValues(alpha: .1),
      borderRadius: BorderRadius.circular(15),
      border: Border.all(color: color.withValues(alpha: .2)),
    ),
    child: Icon(icon, color: color, size: 24),
  );
}
