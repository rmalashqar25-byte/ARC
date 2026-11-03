import 'dart:convert';

import 'package:arc/api_config.dart';
import 'package:arc/frontend/arc_design.dart';
import 'package:arc/frontend/user_messages.dart';
import 'package:arc/frontend/external_links.dart';
import 'package:arc/android_automation.dart';
import 'package:arc/frontend/pages/accessibility_settings_page.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

typedef PluginAccessTokenProvider = Future<String?> Function();
typedef PluginExternalLauncher = Future<bool> Function(Uri uri);
typedef PluginDevicePermissionProvider = Future<bool> Function();

class Plugins extends StatefulWidget {
  const Plugins({
    super.key,
    this.client,
    this.accessTokenProvider,
    this.externalLauncher,
    this.devicePermissionProvider,
  });

  final http.Client? client;
  final PluginAccessTokenProvider? accessTokenProvider;
  final PluginExternalLauncher? externalLauncher;
  final PluginDevicePermissionProvider? devicePermissionProvider;

  @override
  State<Plugins> createState() => _PluginsState();
}

class _PluginsState extends State<Plugins> with WidgetsBindingObserver {
  late final http.Client _client;
  late final bool _ownsClient;
  List<_PluginInfo> _plugins = const [];
  bool _loading = true;
  String? _busyPlugin;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _ownsClient = widget.client == null;
    _client = widget.client ?? http.Client();
    _loadPlugins();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _loadPlugins(silent: true);
  }

  Future<String?> _accessToken() async {
    if (widget.accessTokenProvider != null) {
      return widget.accessTokenProvider!.call();
    }
    return ApiConfig.sessionToken;
  }

  Future<Map<String, String>> _headers({bool json = false}) async {
    final token = await _accessToken();
    if (token == null || token.isEmpty) {
      throw StateError('Temporary session is unavailable. Restart the app.');
    }
    return {
      'X-Arc-Session': token,
      if (json) 'Content-Type': 'application/json',
    };
  }

  Future<void> _loadPlugins({bool silent = false}) async {
    if (!silent && mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final response = await _client
          .get(
            ApiConfig.endpoint('/plugins/catalog'),
            headers: await _headers(),
          )
          .timeout(const Duration(seconds: 20));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw http.ClientException(_responseError(response));
      }
      final body = jsonDecode(response.body);
      final rawPlugins = body is Map ? body['plugins'] : null;
      if (rawPlugins is! List) {
        throw const FormatException('Invalid plugin catalog response');
      }
      final plugins = rawPlugins
          .whereType<Map>()
          .map(_PluginInfo.fromJson)
          .toList();
      final androidEnabled =
          await (widget.devicePermissionProvider ??
              AndroidAutomation.isEnabled)();
      if (!mounted) return;
      setState(() {
        _plugins = plugins
            .map(
              (plugin) => plugin.installKind == 'device_permission'
                  ? plugin.copyWith(
                      installed: androidEnabled,
                      ready: androidEnabled,
                    )
                  : plugin,
            )
            .toList();
        _loading = false;
        _error = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Your tools could not be loaded. Please try again.';
      });
    }
  }

  String _responseError(http.Response response) =>
      requestFailureMessage(response.statusCode);

  Future<bool> _openExternal(Uri uri) async {
    if (widget.externalLauncher != null) {
      return widget.externalLauncher!.call(uri);
    }
    return launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Future<void> _connectGithub(_PluginInfo plugin) async {
    if (_busyPlugin != null || plugin.available == false) return;
    setState(() => _busyPlugin = plugin.id);
    try {
      final response = await _client
          .get(ApiConfig.endpoint('/github/connect'), headers: await _headers())
          .timeout(const Duration(seconds: 20));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw http.ClientException(_responseError(response));
      }
      final body = jsonDecode(response.body);
      if (body is! Map) throw const FormatException('Invalid GitHub response');
      final authorizationUrl = trustedExternalUri(
        body['authorization_url']?.toString(),
        'github.com',
      );
      final installationUrl = trustedExternalUri(
        body['installation_url']?.toString(),
        'github.com',
      );
      if (authorizationUrl == null || installationUrl == null || !mounted) {
        throw const FormatException('GitHub setup URLs are unavailable');
      }
      await showModalBottomSheet<void>(
        context: context,
        backgroundColor: const Color(0xFF1D1D1D),
        showDragHandle: true,
        builder: (sheetContext) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Connect GitHub',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'First install the ARC GitHub App on the repositories you choose. Then authorize your GitHub account.',
                  style: TextStyle(color: Color(0xFFB6B6B6), height: 1.4),
                ),
                const SizedBox(height: 18),
                OutlinedButton.icon(
                  onPressed: () => _launchWithFeedback(installationUrl),
                  icon: const Icon(Icons.install_mobile_outlined),
                  label: const Text('1. Install GitHub App'),
                ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: () => _launchWithFeedback(authorizationUrl),
                  icon: const Icon(Icons.link_rounded),
                  label: const Text('2. Authorize GitHub'),
                ),
              ],
            ),
          ),
        ),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('GitHub could not be connected. Please try again.'),
        ),
      );
    } finally {
      if (mounted) setState(() => _busyPlugin = null);
    }
  }

  Future<void> _launchWithFeedback(Uri uri) async {
    final opened = await _openExternal(uri);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the setup page.')),
      );
    }
  }

  Future<void> _disconnectGithub(_PluginConnection connection) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Disconnect GitHub?'),
        content: Text(
          'Remove ARC’s connection to ${connection.accountLogin}? You can also revoke the GitHub App on GitHub.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Disconnect'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _busyPlugin = 'github');
    try {
      final response = await _client
          .delete(
            ApiConfig.endpoint(
              '/github/connections/${connection.installationId}',
            ),
            headers: await _headers(),
          )
          .timeout(const Duration(seconds: 20));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw http.ClientException(_responseError(response));
      }
      await _loadPlugins(silent: true);
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('GitHub could not be disconnected. Please try again.'),
        ),
      );
    } finally {
      if (mounted) setState(() => _busyPlugin = null);
    }
  }

  Future<void> _openAndroidControl() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const AccessibilitySettingsPage()),
    );
    await _loadPlugins(silent: true);
  }

  Future<void> _connectTerminal() async {
    if (_busyPlugin != null) return;
    setState(() => _busyPlugin = 'terminal_run');
    try {
      final response = await _client
          .post(
            ApiConfig.endpoint('/plugins/terminal/auto-connect'),
            headers: await _headers(json: true),
            body: jsonEncode({}),
          )
          .timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) {
        throw http.ClientException('Terminal connection was not accepted');
      }
      await _loadPlugins(silent: true);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Open ARC with the local launcher to connect its terminal.',
            ),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busyPlugin = null);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (_ownsClient) _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Agent tools'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : _loadPlugins,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          color: arcLime,
          onRefresh: _loadPlugins,
          child: LayoutBuilder(
            builder: (context, viewport) => ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: EdgeInsets.symmetric(
                horizontal: viewport.maxWidth > 1328
                    ? (viewport.maxWidth - 1280) / 2
                    : viewport.maxWidth < 600
                    ? 16
                    : 24,
                vertical: 24,
              ),
              children: [
                const Text(
                  'YOUR TOOLKIT',
                  style: TextStyle(
                    color: arcLime,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Give your team the right tools.',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 30,
                    height: 1.15,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -.7,
                  ),
                ),
                const SizedBox(height: 10),
                const Text(
                  'Discover what your team can do. Use included tools or connect your favorite services.',
                  style: TextStyle(color: Color(0xFFA7B0A5), height: 1.5),
                ),
                if (!_loading) ...[
                  const SizedBox(height: 18),
                  Text(
                    '${_plugins.length} tools  ·  ${_plugins.where((p) => p.ready == true).length} ready to use',
                    style: const TextStyle(
                      color: Color(0xFF899586),
                      fontSize: 12,
                    ),
                  ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 20),
                  _ErrorCard(message: _error!, retry: _loadPlugins),
                ],
                if (_loading) ...[
                  const SizedBox(height: 48),
                  const Center(
                    child: CircularProgressIndicator(color: arcLime),
                  ),
                ] else if (_plugins.isEmpty && _error == null) ...[
                  const SizedBox(height: 28),
                  const Text(
                    'Your tools will appear here when available.',
                    style: TextStyle(color: Color(0xFFA7B0A5)),
                  ),
                ] else ...[
                  const SizedBox(height: 24),
                  _PluginGrid(
                    children: _plugins
                        .map(
                          (plugin) => _PluginCard(
                            key: ValueKey('plugin-${plugin.id}'),
                            plugin: plugin,
                            busy: _busyPlugin == plugin.id,
                            onConnectGithub: () => _connectGithub(plugin),
                            onDisconnectGithub: _disconnectGithub,
                            onOpenAndroidControl: _openAndroidControl,
                            onConnectTerminal: _connectTerminal,
                          ),
                        )
                        .toList(),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PluginInfo {
  const _PluginInfo({
    required this.id,
    required this.displayName,
    required this.description,
    required this.risk,
    required this.installKind,
    required this.installed,
    required this.ready,
    required this.available,
    required this.connections,
    this.connectionState = '',
    this.connectionHint = '',
  });

  factory _PluginInfo.fromJson(Map<dynamic, dynamic> json) {
    final rawConnections = json['connections'];
    return _PluginInfo(
      id: json['id']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? 'Tool',
      description: json['description']?.toString() ?? '',
      risk: json['risk']?.toString() ?? 'unknown',
      installKind: json['install_kind']?.toString() ?? 'built_in',
      installed: json['installed'] as bool?,
      ready: json['ready'] as bool?,
      available: json['available'] as bool?,
      connections: rawConnections is List
          ? rawConnections
                .whereType<Map>()
                .map(_PluginConnection.fromJson)
                .toList()
          : const [],
      connectionState: json['connection_state']?.toString() ?? '',
      connectionHint: json['connection_hint']?.toString() ?? '',
    );
  }

  final String id;
  final String displayName;
  final String description;
  final String risk;
  final String installKind;
  final bool? installed;
  final bool? ready;
  final bool? available;
  final List<_PluginConnection> connections;
  final String connectionState;
  final String connectionHint;

  _PluginInfo copyWith({bool? installed, bool? ready}) {
    return _PluginInfo(
      id: id,
      displayName: displayName,
      description: description,
      risk: risk,
      installKind: installKind,
      installed: installed ?? this.installed,
      ready: ready ?? this.ready,
      available: available,
      connections: connections,
      connectionState: connectionState,
      connectionHint: connectionHint,
    );
  }

  String get statusLabel {
    if (installKind == 'local_terminal' &&
        ready != true &&
        connectionState == 'offline') {
      return 'Offline';
    }
    if (installKind == 'managed_connector' && ready != true) {
      return 'Not available yet';
    }
    if (installKind == 'github_app' && available == false) {
      return 'Not available yet';
    }
    if (installed == true && ready == false) {
      return 'Connection incomplete';
    }
    if (ready == true) return 'Ready';
    return 'Not connected';
  }

  Color get statusColor {
    if (ready == true) return const Color(0xFF35C58A);
    if (installed == true) return Colors.orangeAccent;
    return const Color(0xFF999999);
  }
}

class _PluginConnection {
  const _PluginConnection({
    required this.installationId,
    required this.accountLogin,
    required this.accountType,
  });

  factory _PluginConnection.fromJson(Map<dynamic, dynamic> json) {
    return _PluginConnection(
      installationId: int.tryParse(json['installation_id'].toString()) ?? 0,
      accountLogin: json['account_login']?.toString() ?? 'GitHub account',
      accountType: json['account_type']?.toString() ?? 'Account',
    );
  }

  final int installationId;
  final String accountLogin;
  final String accountType;
}

class _PluginGrid extends StatelessWidget {
  const _PluginGrid({required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final columns = constraints.maxWidth >= 820
          ? 3
          : constraints.maxWidth >= 540
          ? 2
          : 1;
      return Column(
        children: [
          for (var start = 0; start < children.length; start += columns)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (var column = 0; column < columns; column++) ...[
                      if (column > 0) const SizedBox(width: 16),
                      Expanded(
                        child: start + column < children.length
                            ? children[start + column]
                            : const SizedBox.shrink(),
                      ),
                    ],
                  ],
                ),
              ),
            ),
        ],
      );
    },
  );
}

class _PluginCard extends StatelessWidget {
  const _PluginCard({
    super.key,
    required this.plugin,
    required this.busy,
    required this.onConnectGithub,
    required this.onDisconnectGithub,
    required this.onOpenAndroidControl,
    required this.onConnectTerminal,
  });

  final _PluginInfo plugin;
  final bool busy;
  final VoidCallback onConnectGithub;
  final ValueChanged<_PluginConnection> onDisconnectGithub;
  final VoidCallback onOpenAndroidControl;
  final VoidCallback onConnectTerminal;

  @override
  Widget build(BuildContext context) {
    final (icon, accent) = _appearance;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: arcPanel,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFF2A322B)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: .1),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: accent.withValues(alpha: .16)),
                ),
                child: Icon(icon, color: accent, size: 24),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Align(
                  alignment: Alignment.topRight,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: plugin.statusColor.withValues(alpha: .08),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      plugin.statusLabel,
                      style: TextStyle(
                        color: plugin.statusColor,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text(
            plugin.displayName,
            style: const TextStyle(
              color: Color(0xFFF0F3ED),
              fontSize: 18,
              fontWeight: FontWeight.w600,
              letterSpacing: -.3,
            ),
          ),
          if (plugin.description.isNotEmpty) ...[
            const SizedBox(height: 9),
            Text(
              plugin.description,
              style: const TextStyle(
                color: Color(0xFFA7B0A5),
                fontSize: 13,
                height: 1.5,
              ),
            ),
          ],
          if (plugin.connectionHint.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              plugin.connectionHint,
              style: const TextStyle(
                color: arcLilac,
                fontSize: 12,
                height: 1.5,
              ),
            ),
          ],
          if (plugin.connections.isNotEmpty) ...[
            const SizedBox(height: 14),
            ...plugin.connections.map(
              (connection) => ListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                leading: const Icon(Icons.link, size: 20, color: arcLime),
                title: Text(
                  connection.accountLogin,
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
                subtitle: Text(
                  connection.accountType,
                  style: const TextStyle(
                    color: Color(0xFF999999),
                    fontSize: 11,
                  ),
                ),
                trailing: IconButton(
                  tooltip: 'Disconnect',
                  onPressed: busy ? null : () => onDisconnectGithub(connection),
                  icon: const Icon(
                    Icons.link_off,
                    size: 20,
                    color: Colors.redAccent,
                  ),
                ),
              ),
            ),
          ],
          const Spacer(),
          const SizedBox(height: 20),
          const Divider(height: 1, color: Color(0xFF2A322B)),
          const SizedBox(height: 12),
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: [
              Text(
                'Risk: ${plugin.risk.replaceAll('_', ' ')}',
                style: const TextStyle(color: Color(0xFF899586), fontSize: 11),
              ),
              _buildAction(),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAction() {
    if (busy) {
      return const SizedBox(
        width: 24,
        height: 24,
        child: CircularProgressIndicator(strokeWidth: 2, color: arcLime),
      );
    }
    if (plugin.installKind == 'local_terminal' && plugin.ready != true) {
      return FilledButton.icon(
        style: FilledButton.styleFrom(
          backgroundColor: arcLime,
          foregroundColor: const Color(0xFF19230F),
        ),
        onPressed: plugin.available == true ? onConnectTerminal : null,
        icon: const Icon(Icons.power_settings_new_rounded, size: 16),
        label: const Text('Turn on'),
      );
    }
    if (plugin.installKind == 'github_app' ||
        plugin.installKind == 'device_permission') {
      final github = plugin.installKind == 'github_app';
      return FilledButton.icon(
        style: FilledButton.styleFrom(
          backgroundColor: arcLime,
          foregroundColor: const Color(0xFF19230F),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        ),
        onPressed: github
            ? (plugin.available == false ? null : onConnectGithub)
            : onOpenAndroidControl,
        icon: Icon(
          plugin.installed == true ? Icons.tune_rounded : Icons.add_rounded,
          size: 16,
        ),
        label: Text(
          plugin.installed == true
              ? 'Manage'
              : github
              ? 'Connect'
              : 'Turn on',
        ),
      );
    }
    if (plugin.ready != true) {
      return const Text(
        'Unavailable',
        style: TextStyle(color: Color(0xFF899586), fontSize: 12),
      );
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(
          Icons.check_circle_outline_rounded,
          size: 16,
          color: arcLime,
        ),
        const SizedBox(width: 5),
        Text(
          plugin.installKind == 'built_in' ? 'Included' : 'Connected',
          style: const TextStyle(color: arcLime, fontSize: 12),
        ),
      ],
    );
  }

  (IconData, Color) get _appearance => switch (plugin.id) {
    'calculator' => (Icons.calculate_outlined, arcLime),
    'finance_summary' => (
      Icons.account_balance_wallet_outlined,
      const Color(0xFF8DDCC0),
    ),
    'workspace_search' => (
      Icons.manage_search_rounded,
      const Color(0xFF97C9F5),
    ),
    'workspace_read' => (Icons.description_outlined, const Color(0xFFA7BDF9)),
    'workspace_update' => (Icons.edit_note_rounded, arcLilac),
    'workspace_delete' => (
      Icons.delete_outline_rounded,
      const Color(0xFFF1AB9F),
    ),
    'workspace_restore' => (
      Icons.restore_page_outlined,
      const Color(0xFF92D8C0),
    ),
    'draft_file' => (Icons.note_add_outlined, const Color(0xFFECC88F)),
    'terminal_run' => (Icons.terminal_rounded, arcLime),
    'finance_connector' => (
      Icons.account_balance_outlined,
      const Color(0xFF8DDCC0),
    ),
    'crm_connector' => (Icons.contacts_outlined, const Color(0xFFE9AFCD)),
    'cloud_connector' => (Icons.cloud_outlined, const Color(0xFF97C9F5)),
    'github' || 'git_publish' => (Icons.code_rounded, arcLilac),
    'delegate_agent' => (Icons.hub_outlined, const Color(0xFFECC88F)),
    'delegate_department' => (Icons.groups_outlined, const Color(0xFFB8C7F7)),
    _ =>
      plugin.installKind == 'device_permission'
          ? (Icons.smartphone_rounded, const Color(0xFF8DDCC0))
          : plugin.id.contains('browser')
          ? (Icons.language_rounded, const Color(0xFF97C9F5))
          : (Icons.extension_outlined, arcLilac),
  };
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.retry});

  final String message;
  final VoidCallback retry;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF512424),
      child: ListTile(
        leading: const Icon(Icons.error_outline, color: Colors.white),
        title: Text(message, style: const TextStyle(color: Colors.white)),
        trailing: TextButton(onPressed: retry, child: const Text('Retry')),
      ),
    );
  }
}
