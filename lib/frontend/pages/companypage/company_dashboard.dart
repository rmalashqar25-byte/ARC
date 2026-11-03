import 'work_board.dart';
import 'package:arc/frontend/user_messages.dart';
import 'package:arc/api_config.dart';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/pages/companypage/market.dart';

import 'package:flutter/material.dart';

class CompanyDashboard extends StatefulWidget {
  const CompanyDashboard({super.key, this.api, this.initialSessionId});

  final CompanyApiClient? api;
  final String? initialSessionId;

  @override
  State<CompanyDashboard> createState() => _CompanyDashboardState();
}

class _CompanyDashboardState extends State<CompanyDashboard> {
  late final CompanyApiClient _api;
  late final bool _ownsApi;
  late String _sessionId;
  CompanyCatalog? _catalog;
  List<CompanyGroup> _groups = const [];
  List<Map<String, dynamic>> _teamMembers = const [];
  bool _loading = true;
  String? _error;
  @override
  void initState() {
    super.initState();
    _ownsApi = widget.api == null;
    _api = widget.api ?? CompanyApiClient();
    _sessionId = widget.initialSessionId ?? ApiConfig.companySessionId;
    _refresh();
  }

  Future<void> _refresh() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final results = await Future.wait<Object>([
        _api.loadCatalog(),
        _api.loadGroups(_sessionId),
      ]);
      List<Map<String, dynamic>> teamMembers = [];
      try {
        final team = await _api.loadProjectTeam(_sessionId);
        teamMembers = (team['members'] as List)
            .map((m) => Map<String, dynamic>.from(m as Map))
            .toList();
      } catch (_) {
        // Older backends can still display the existing company groups.
      }
      if (!mounted) return;
      setState(() {
        _catalog = results[0] as CompanyCatalog;
        _groups = results[1] as List<CompanyGroup>;
        _teamMembers = teamMembers;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = requestFailureMessage();
      });
    }
  }

  String _agentName(String id) => _catalog?.agent(id)?.name ?? id;

  @override
  void dispose() {
    if (_ownsApi) _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF090909),
      appBar: AppBar(
        backgroundColor: const Color(0xFF090909),
        foregroundColor: Colors.white,
        title: const Text('ARC Company'),
        actions: [
          IconButton(
            tooltip: 'Market',
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (context) =>
                      Market(api: _api, sessionId: _sessionId),
                ),
              );
              if (mounted) _refresh();
            },
            icon: const Icon(Icons.add_business_outlined),
          ),
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : _refresh,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1080),
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                children: [
                  FilledButton.icon(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => WorkBoard(sessionId: _sessionId),
                      ),
                    ),
                    icon: const Icon(Icons.work_history_outlined),
                    label: const Text('Open company work board'),
                  ),
                  const SizedBox(height: 20),
                  if (_teamMembers.isNotEmpty) ...[
                    const Text(
                      'Your project team',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: _teamMembers.map((m) {
                        const names = {
                          'gpt_sol': 'GPT Sol',
                          'claude': 'Claude',
                          'gemini': 'Gemini',
                          'deepseek': 'DeepSeek',
                          'qwen': 'Qwen',
                          'mistral': 'Mistral',
                          'llama': 'Llama',
                          'grok': 'Grok',
                        };
                        final role =
                            _catalog?.agent(m['role_id'] as String)?.jobTitle ??
                            m['role_id'];
                        return Chip(
                          label: Text(
                            '${names[m['agent_id']] ?? m['agent_id']} · $role',
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 24),
                  ],
                  const Text(
                    'Your company',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Talk to the CEO in the main AI chat. Explore the marketplace and watch teams form here as work is delegated.',
                    style: TextStyle(color: Color(0xFFAAAAAA), height: 1.45),
                  ),

                  const SizedBox(height: 18),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: FilledButton.icon(
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) =>
                              Market(api: _api, sessionId: _sessionId),
                        ),
                      ),
                      icon: const Icon(Icons.storefront_outlined),
                      label: const Text('Explore team marketplace'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  const SizedBox(height: 26),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: Text(
                        _error!,
                        style: const TextStyle(color: Colors.redAccent),
                      ),
                    ),
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Company groups',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      Text(
                        '${_groups.length}',
                        style: const TextStyle(color: Color(0xFF8F8F8F)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_loading && _groups.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (_groups.isEmpty)
                    _EmptyGroups()
                  else
                    ..._groups.map(
                      (group) => _GroupSummaryCard(
                        group: group,
                        agentName: _agentName,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _EmptyGroups extends StatelessWidget {
  const _EmptyGroups();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: const Color(0xFF151515),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF2B2B2B)),
      ),
      child: Column(
        children: [
          const Icon(Icons.groups_outlined, color: Color(0xFF777777), size: 42),
          const SizedBox(height: 12),
          const Text(
            'No groups yet',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          const Text(
            'Ask the CEO in the main AI chat to start a project. Groups appear here when work is delegated.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF999999), height: 1.4),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _GroupSummaryCard extends StatelessWidget {
  const _GroupSummaryCard({required this.group, required this.agentName});

  final CompanyGroup group;
  final String Function(String id) agentName;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF1B1B1B),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.groups_2_outlined, color: Color(0xFFFFB86C)),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    group.name,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Text(
                  '${group.members.length} members',
                  style: const TextStyle(color: Color(0xFF8F8F8F)),
                ),
              ],
            ),
            if (group.objective.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                group.objective,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Color(0xFFB5B5B5), height: 1.35),
              ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 7,
              runSpacing: 7,
              children: group.members
                  .map(
                    (member) => Chip(
                      visualDensity: VisualDensity.compact,
                      avatar: const Icon(Icons.person, size: 16),
                      label: Text(
                        member.displayName ?? agentName(member.agentId),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }
}
