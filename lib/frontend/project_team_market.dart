import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'company_api_client.dart';
import 'arc_design.dart';
import 'market_departments.dart';
import 'external_links.dart';

String modelTokenPrice(Map<String, dynamic> model) {
  final input = model['input_price_per_million'];
  final output = model['output_price_per_million'];
  if (input == null || output == null) {
    return model['model_id'] == null
        ? '\$${model['price']} / month · Demo'
        : 'Token pricing not listed';
  }
  String money(num n) => n == 0
      ? '0'
      : n.toStringAsFixed(n < .01 ? 4 : 2).replaceAll(RegExp(r'\.?0+$'), '');
  return '\$${money(input as num)} in · \$${money(output as num)} out / 1M tokens';
}

class ProjectTeamMarket extends StatefulWidget {
  const ProjectTeamMarket({
    super.key,
    required this.api,
    required this.sessionId,
    required this.roles,
    this.department,
  });
  final CompanyApiClient api;
  final String sessionId;
  final List<CompanyAgent> roles;
  final String? department;
  @override
  State<ProjectTeamMarket> createState() => _ProjectTeamMarketState();
}

class _ProjectTeamMarketState extends State<ProjectTeamMarket> {
  List<Map<String, dynamic>> _models = [];
  List<Map<String, String>> _members = [];
  final Set<String> _compare = {};
  String _mode = 'undecided', _query = '', _sort = 'compatible';
  String? _error;
  bool _busy = false,
      _connected = false,
      _toolsOnly = false,
      _reasoningOnly = false,
      _allWork = false;
  int _visible = 24;
  bool _loading = true;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool refresh = false}) async {
    if (mounted) setState(() => _loading = true);
    if (_models.isEmpty) {
      final bytes = await rootBundle.load(
        'lib/backend/company/model_catalog.json',
      );
      final bundled =
          jsonDecode(
                utf8.decode(
                  bytes.buffer.asUint8List(
                    bytes.offsetInBytes,
                    bytes.lengthInBytes,
                  ),
                ),
              )
              as List;
      if (!mounted) return;
      setState(
        () => _models = bundled
            .map((a) => Map<String, dynamic>.from(a as Map))
            .toList(),
      );
    }
    try {
      final models = await widget.api.loadMarketplace(refresh: refresh);
      final team = await widget.api.loadProjectTeam(widget.sessionId);
      if (!mounted) return;
      setState(() {
        _models = models;
        _mode = team['mode'] as String;
        _members = (team['members'] as List)
            .map((m) => Map<String, String>.from(m as Map))
            .toList();
        _connected = true;
        _error = null;
      });
    } catch (_) {
      if (mounted) {
        setState(() {
          _connected = false;
          _error =
              'You’re browsing the researched catalog offline. Connect the updated marketplace to add models or refresh availability.';
        });
      }
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _save(String mode, List<Map<String, String>> members) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.saveProjectTeam(widget.sessionId, mode, members);
      if (mounted) {
        setState(() {
          _members = members;
          _mode = mode;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is CompanyApiException
              ? error.message
              : 'Could not save your team. Please retry when connected.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _context(Map<String, dynamic> m) =>
      (m['context_length'] as num? ?? 0) > 0
      ? '${m['context_length']} tokens'
      : 'Not listed';
  List<CompanyAgent> get _roles {
    final department = marketDepartment(widget.department);
    final all = widget.roles.where((r) => r.id != 'ceo').toList();
    return department == null
        ? all
        : all.where((r) => department.roles.contains(r.id)).toList();
  }

  Future<void> _details(Map<String, dynamic> model) async {
    final roles = _roles;
    final department = marketDepartment(widget.department);
    var roleId = department?.roles.first ?? model['role_id'] as String;
    if (roles.isNotEmpty && !roles.any((r) => r.id == roleId)) {
      roleId = roles.first.id;
    }
    final added = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          backgroundColor: arcPanel,
          title: Text(model['name'] as String),
          content: SizedBox(
            width: 540,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (model['model_id'] != null)
                    Text(
                      model['model_id'] as String,
                      style: const TextStyle(color: arcLilac, fontSize: 12),
                    ),
                  const SizedBox(height: 14),
                  Text(
                    model['summary'] as String,
                    style: const TextStyle(height: 1.6),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    modelTokenPrice(model),
                    style: const TextStyle(
                      color: arcLime,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (model['model_id'] != null) ...[
                    Text(
                      'Inputs: ${(model['input_modalities'] as List? ?? []).join(', ')}',
                    ),
                    Text(
                      'Outputs: ${(model['output_modalities'] as List? ?? []).join(', ')}',
                    ),
                    Text('Context: ${_context(model)}'),
                    const SizedBox(height: 16),
                    const Text(
                      'BEFORE YOU CHOOSE',
                      style: TextStyle(
                        color: arcLilac,
                        fontSize: 11,
                        letterSpacing: 1.5,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      model['considerations'] as String? ?? '',
                      style: const TextStyle(
                        color: Colors.white60,
                        height: 1.5,
                      ),
                    ),
                    if (model['agent_compatible'] == false)
                      const Padding(
                        padding: EdgeInsets.only(top: 12),
                        child: Text(
                          'This model is listed for discovery. ARC company agents require text output and tool calling, so this model cannot be added as a company worker.',
                          style: TextStyle(color: Colors.amber, height: 1.5),
                        ),
                      ),
                    const SizedBox(height: 14),
                    Text(
                      'Catalog checked: ${model['checked_on'] ?? 'Unknown'}',
                      style: const TextStyle(
                        color: Colors.white54,
                        fontSize: 12,
                      ),
                    ),
                    TextButton.icon(
                      onPressed:
                          trustedExternalUri(
                                model['source_url']?.toString(),
                                'openrouter.ai',
                              ) ==
                              null
                          ? null
                          : () => launchUrl(
                              trustedExternalUri(
                                model['source_url']?.toString(),
                                'openrouter.ai',
                              )!,
                              mode: LaunchMode.externalApplication,
                            ),
                      icon: const Icon(Icons.open_in_new, size: 16),
                      label: const Text('Read the model source'),
                    ),
                    const Divider(),
                  ],
                  if (roles.isNotEmpty)
                    DropdownButtonFormField<String>(
                      initialValue: roleId,
                      isExpanded: true,
                      decoration: const InputDecoration(
                        labelText: 'Role in your company',
                      ),
                      items: roles
                          .map(
                            (r) => DropdownMenuItem(
                              value: r.id,
                              child: Text(
                                r.jobTitle,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (v) => update(() => roleId = v!),
                    )
                  else
                    Text('Company role: ${department?.name ?? model['role']}'),
                  const SizedBox(height: 14),
                  Text(
                    !_connected
                        ? 'Preview only until the marketplace connects.'
                        : model['configured'] == true
                        ? 'Uses this exact model ID through your connected provider. Availability, usage limits, and API charges still apply. Adding it does not buy a subscription.'
                        : 'This model is not connected for company work. You can still review and compare its capabilities.',
                    style: const TextStyle(color: Colors.white60, height: 1.5),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Close'),
            ),
            FilledButton(
              onPressed: _connected && model['configured'] == true
                  ? () => Navigator.pop(context, true)
                  : null,
              child: const Text('Add to my project'),
            ),
          ],
        ),
      ),
    );
    if (added == true && mounted) {
      await _save('manual', [
        ..._members.where((m) => m['role_id'] != roleId),
        {'agent_id': model['id'] as String, 'role_id': roleId},
      ]);
    }
  }

  void _compareModels() {
    final models = _models.where((m) => _compare.contains(m['id'])).toList();
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Compare the facts'),
        content: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: [
              const DataColumn(label: Text('Capability')),
              ...models.map(
                (m) => DataColumn(
                  label: SizedBox(
                    width: 150,
                    child: Text(m['name'] as String, maxLines: 3),
                  ),
                ),
              ),
            ],
            rows: [
              for (final feature in [
                'Context',
                'Tool calling',
                'Reasoning',
                'Inputs',
                'Outputs',
                'Token prices',
              ])
                DataRow(
                  cells: [
                    DataCell(Text(feature)),
                    ...models.map(
                      (m) => DataCell(
                        SizedBox(
                          width: 150,
                          child: Text(switch (feature) {
                            'Context' => _context(m),
                            'Tool calling' =>
                              m['supports_tools'] == true
                                  ? 'Listed'
                                  : 'Not listed',
                            'Reasoning' =>
                              m['supports_reasoning'] == true
                                  ? 'Supported'
                                  : 'Not listed',
                            'Inputs' =>
                              (m['input_modalities'] as List? ?? []).join(', '),
                            'Outputs' =>
                              (m['output_modalities'] as List? ?? []).join(
                                ', ',
                              ),
                            _ => modelTokenPrice(m),
                          }),
                        ),
                      ),
                    ),
                  ],
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Done'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final department = marketDepartment(widget.department);
    final filtered = _models.where((m) {
      final categories = m['categories'] as List?;
      return (_allWork ||
              department == null ||
              categories == null ||
              categories.contains(department.id)) &&
          (!_toolsOnly || m['supports_tools'] == true) &&
          (!_reasoningOnly || m['supports_reasoning'] == true) &&
          '${m['name']} ${m['id']} ${m['provider']} ${m['summary']}'
              .toLowerCase()
              .contains(_query);
    }).toList();
    filtered.sort((a, b) {
      if (_sort == 'compatible') {
        final compatibility = (b['agent_compatible'] == true ? 1 : 0).compareTo(
          a['agent_compatible'] == true ? 1 : 0,
        );
        if (compatibility != 0) return compatibility;
      }
      return switch (_sort) {
        'price' =>
          ((a['input_price_per_million'] as num?) ?? double.infinity).compareTo(
            (b['input_price_per_million'] as num?) ?? double.infinity,
          ),
        'context' => ((b['context_length'] as num?) ?? 0).compareTo(
          (a['context_length'] as num?) ?? 0,
        ),
        _ => ((b['created'] as num?) ?? 0).compareTo(
          (a['created'] as num?) ?? 0,
        ),
      };
    });
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_loading) const LinearProgressIndicator(color: arcLime),
        Text(
          department == null
              ? 'Every model.\nA clearer choice.'
              : 'AI for ${department.name.toLowerCase()}.',
          style: const TextStyle(
            fontSize: 36,
            fontWeight: FontWeight.w600,
            height: 1.15,
            letterSpacing: -1,
          ),
        ),
        const SizedBox(height: 14),
        Text(
          '${_models.length} individual models in the OpenRouter catalog. Compare real capabilities and token rates, then choose a company role.',
          style: const TextStyle(color: Colors.white60, height: 1.6),
        ),
        const SizedBox(height: 10),
        const Text(
          'Work matches are capability-based suggestions, not quality rankings. Research still needs sources and fact checking.',
          style: TextStyle(color: Colors.white54, fontSize: 12, height: 1.5),
        ),
        const SizedBox(height: 20),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            ChoiceChip(
              label: const Text('I choose my team'),
              selected: _mode == 'manual',
              onSelected: _busy || !_connected
                  ? null
                  : (_) => _save('manual', _members),
            ),
            ChoiceChip(
              label: const Text('Let the CEO choose'),
              selected: _mode == 'ceo',
              onSelected: _busy || !_connected
                  ? null
                  : (_) => _save('ceo', _members),
            ),
            IconButton(
              tooltip: 'Refresh model catalog',
              onPressed: _busy ? null : () => _load(refresh: true),
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        if (_busy) const LinearProgressIndicator(),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: ArcNotice(message: _error!, onRetry: _load),
          ),
        if (_members.isNotEmpty) ...[
          const SizedBox(height: 14),
          const Text(
            'YOUR PROJECT TEAM',
            style: TextStyle(color: arcLime, fontSize: 11, letterSpacing: 1.5),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _members.map((m) {
              final model = _models
                  .where((a) => a['id'] == m['agent_id'])
                  .firstOrNull;
              final role = widget.roles
                  .where((r) => r.id == m['role_id'])
                  .firstOrNull;
              return InputChip(
                label: Text(
                  '${model?['name'] ?? m['agent_id']} · ${role?.jobTitle ?? m['role_id']}',
                ),
                onDeleted: _busy
                    ? null
                    : () => _save(
                        'manual',
                        _members.where((a) => a != m).toList(),
                      ),
              );
            }).toList(),
          ),
        ],
        const SizedBox(height: 22),
        TextField(
          onChanged: (v) => setState(() {
            _query = v.toLowerCase();
            _visible = 24;
          }),
          decoration: InputDecoration(
            hintText: 'Search model name, version, provider, or capability',
            prefixIcon: const Icon(Icons.search),
            filled: true,
            fillColor: arcPanel,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(18),
              borderSide: BorderSide.none,
            ),
          ),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (department != null)
              FilterChip(
                label: const Text('All models'),
                selected: _allWork,
                onSelected: (v) => setState(() {
                  _allWork = v;
                  _visible = 24;
                }),
              ),
            FilterChip(
              label: const Text('Tool calling'),
              selected: _toolsOnly,
              onSelected: (v) => setState(() {
                _toolsOnly = v;
                _visible = 24;
              }),
            ),
            FilterChip(
              label: const Text('Reasoning'),
              selected: _reasoningOnly,
              onSelected: (v) => setState(() {
                _reasoningOnly = v;
                _visible = 24;
              }),
            ),
            SizedBox(
              width: 190,
              child: DropdownButtonFormField<String>(
                initialValue: _sort,
                isExpanded: true,
                decoration: const InputDecoration(
                  isDense: true,
                  border: InputBorder.none,
                ),
                items: const [
                  DropdownMenuItem(
                    value: 'compatible',
                    child: Text('Company workers first'),
                  ),
                  DropdownMenuItem(
                    value: 'newest',
                    child: Text('Newest first'),
                  ),
                  DropdownMenuItem(
                    value: 'price',
                    child: Text('Lowest input rate'),
                  ),
                  DropdownMenuItem(
                    value: 'context',
                    child: Text('Largest context'),
                  ),
                ],
                onChanged: (v) => setState(() => _sort = v!),
              ),
            ),
            if (_compare.isNotEmpty)
              OutlinedButton(
                onPressed: _compareModels,
                child: Text('Compare (${_compare.length}/3)'),
              ),
          ],
        ),
        const SizedBox(height: 18),
        Text(
          '${filtered.length} models match · Showing ${filtered.length < _visible ? filtered.length : _visible}',
          style: const TextStyle(color: Colors.white54, fontSize: 12),
        ),
        const SizedBox(height: 16),
        if (filtered.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Text(
              'No matches. Try another model name or clear a filter.',
            ),
          ),
        LayoutBuilder(
          builder: (context, bounds) {
            final columns = bounds.maxWidth >= 1000
                ? 3
                : bounds.maxWidth >= 620
                ? 2
                : 1;
            final width = (bounds.maxWidth - 14 * (columns - 1)) / columns;
            return Wrap(
              spacing: 14,
              runSpacing: 14,
              children: filtered
                  .take(_visible)
                  .map(
                    (m) => SizedBox(
                      width: width,
                      child: Card(
                        color: arcPanel,
                        margin: EdgeInsets.zero,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(22),
                          side: const BorderSide(color: Color(0xFF30382F)),
                        ),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(22),
                          onTap: _busy ? null : () => _details(m),
                          child: Padding(
                            padding: const EdgeInsets.all(20),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '${m['provider'] ?? 'MODEL'}'.toUpperCase(),
                                  style: const TextStyle(
                                    color: arcLilac,
                                    fontSize: 10,
                                    letterSpacing: 1.5,
                                  ),
                                ),
                                const SizedBox(height: 10),
                                Text(
                                  m['name'] as String,
                                  style: const TextStyle(
                                    fontSize: 21,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 14),
                                Text(
                                  m['summary'] as String,
                                  style: const TextStyle(
                                    color: Colors.white60,
                                    height: 1.6,
                                  ),
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  modelTokenPrice(m),
                                  style: const TextStyle(
                                    color: arcLime,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 10),
                                Text(
                                  !_connected
                                      ? 'Catalog preview · View details'
                                      : m['configured'] == true
                                      ? 'Tool-compatible · Provider connected'
                                      : 'Browse & compare',
                                  style: const TextStyle(
                                    color: Colors.white54,
                                    fontSize: 11,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: TextButton.icon(
                                    onPressed: () => setState(() {
                                      final id = m['id'] as String;
                                      if (_compare.contains(id)) {
                                        _compare.remove(id);
                                      } else if (_compare.length < 3) {
                                        _compare.add(id);
                                      } else {
                                        ScaffoldMessenger.of(
                                          context,
                                        ).showSnackBar(
                                          const SnackBar(
                                            content: Text(
                                              'Compare up to three models at a time.',
                                            ),
                                          ),
                                        );
                                      }
                                    }),
                                    icon: Icon(
                                      _compare.contains(m['id'])
                                          ? Icons.check_circle
                                          : Icons.add_chart,
                                      size: 16,
                                    ),
                                    label: Text(
                                      _compare.contains(m['id'])
                                          ? 'In comparison'
                                          : 'Compare',
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  )
                  .toList(),
            );
          },
        ),
        if (_visible < filtered.length)
          Padding(
            padding: const EdgeInsets.only(top: 24),
            child: Center(
              child: OutlinedButton.icon(
                onPressed: () => setState(() => _visible += 24),
                icon: const Icon(Icons.expand_more),
                label: const Text('Show 24 more models'),
              ),
            ),
          ),
        const SizedBox(height: 24),
      ],
    );
  }
}
