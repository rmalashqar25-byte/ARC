import 'package:arc/api_config.dart';
import 'package:arc/frontend/arc_design.dart';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/project_team_market.dart';
import 'package:arc/frontend/talent_profile_editor.dart';
import 'package:arc/frontend/market_departments.dart';
import 'package:arc/frontend/market_work_picker.dart';
import 'package:flutter/material.dart';

class Market extends StatefulWidget {
  const Market({super.key, this.api, this.sessionId, this.initialKind});
  final CompanyApiClient? api;
  final String? sessionId;
  final String? initialKind;
  @override
  State<Market> createState() => _MarketState();
}

class _MarketState extends State<Market> {
  late final CompanyApiClient _api;
  late final String _sessionId;
  final _search = TextEditingController();
  List<CompanyAgent> _roles = [];
  List<Map<String, dynamic>> _people = [];
  List<Map<String, dynamic>> _employees = [];
  Map<String, dynamic>? _myProfile;
  String? _kind, _error, _department;
  bool _loading = false;
  bool _availableOnly = false;
  bool _sortByRate = false;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? CompanyApiClient();
    _sessionId = widget.sessionId ?? ApiConfig.companySessionId;
    _kind = widget.initialKind;
    if (_kind != null) _load();
  }

  @override
  void dispose() {
    _search.dispose();
    if (widget.api == null) _api.close();
    super.dispose();
  }

  Future<void> _open(String kind) async {
    setState(() {
      _kind = kind;
      _error = null;
      _search.clear();
    });
    await _load();
  }

  Future<void> _load() async {
    final kind = _kind;
    if (kind == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (kind == 'ai') {
        final catalog = await _api.loadCatalog();
        if (mounted && _kind == kind) setState(() => _roles = catalog.agents);
      } else if (kind == 'employee') {
        final employees = await _api.loadOwnEmployees(_sessionId);
        if (mounted && _kind == kind) setState(() => _employees = employees);
      } else {
        final results = await Future.wait<Object?>([
          _api.loadTalent(),
          _api.loadMyTalentProfile(),
        ]);
        if (mounted && _kind == kind) {
          setState(() {
            _people = results[0] as List<Map<String, dynamic>>;
            _myProfile = results[1] as Map<String, dynamic>?;
          });
        }
      }
    } catch (_) {
      if (mounted && _kind == kind && kind != 'ai') {
        setState(() {
          _error =
              'We can’t load the talent directory right now. Your connection to the updated marketplace service is needed to browse or publish profiles.';
        });
      }
    } finally {
      if (mounted && _kind == kind) setState(() => _loading = false);
    }
  }

  Future<void> _editProfile() async {
    // The editor remains available for drafting and previewing even offline.
    Map<String, dynamic>? mine = _myProfile;
    try {
      mine = await _api.loadMyTalentProfile();
    } catch (_) {
      /* Draft offline. */
    }
    if (!mounted) return;
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => TalentProfileEditor(
          api: _api,
          profile: mine,
          department: _department ?? 'general',
        ),
      ),
    );
    if (saved == true && mounted) await _open('human');
  }

  Future<void> _addEmployee() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => TalentProfileEditor(
          api: _api,
          employee: true,
          department: _department ?? 'general',
          sessionId: _sessionId,
        ),
      ),
    );
    if (saved == true && mounted) await _open('employee');
  }

  Future<void> _viewPerson(
    Map<String, dynamic> person, {
    bool employee = false,
  }) async {
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: arcPanel,
        title: Text(person['name'] as String),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  person['role'] as String,
                  style: const TextStyle(color: arcLilac, fontSize: 18),
                ),
                const SizedBox(height: 18),
                Text(
                  person['summary'] as String,
                  style: const TextStyle(height: 1.6),
                ),
                const SizedBox(height: 18),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: (person['skills'] as List? ?? [])
                      .map((s) => Chip(label: Text('$s')))
                      .toList(),
                ),
                const SizedBox(height: 18),
                Text(
                  talentPrice(person),
                  style: const TextStyle(color: arcLime, fontSize: 22),
                ),
                const SizedBox(height: 8),
                Text(_availability(person)),
                if (person['is_example'] != true) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Job capacity: ${person['job_capacity'] ?? 3} active jobs',
                    style: const TextStyle(color: arcLilac),
                  ),
                ],
                const SizedBox(height: 14),
                Text(
                  person['is_example'] == true
                      ? 'Example profile. Maya is fictional, and this rate is illustrative. Add your own employee or publish your skills to create a real profile.'
                      : 'Rates and experience are provided by the profile owner. A saved brief does not send a message or create a contract.',
                  style: const TextStyle(
                    color: Colors.white54,
                    fontSize: 12,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
          if (person['is_example'] == true)
            FilledButton.icon(
              onPressed: () {
                Navigator.pop(context);
                _addEmployee();
              },
              icon: const Icon(Icons.person_add_alt_1),
              label: const Text('Add my employee'),
            )
          else if (person['is_mine'] == true && !employee)
            FilledButton(
              onPressed: () {
                Navigator.pop(context);
                _editProfile();
              },
              child: const Text('Edit my profile'),
            )
          else
            FilledButton(
              onPressed: person['availability'] == 'unavailable'
                  ? null
                  : () {
                      Navigator.pop(context);
                      _prepareBrief(person, employee: employee);
                    },
              child: Text(
                employee
                    ? 'Prepare an employee task'
                    : 'Prepare a project brief',
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _prepareBrief(
    Map<String, dynamic> person, {
    bool employee = false,
  }) async {
    final task = TextEditingController();
    var busy = false;
    String? error;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: Text('A brief for ${person['name']}'),
          content: SizedBox(
            width: 460,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'Describe the outcome, scope, and timing. This saves a private draft in your project.',
                  ),
                  const SizedBox(height: 18),
                  TextField(
                    controller: task,
                    maxLines: 5,
                    maxLength: 8000,
                    decoration: const InputDecoration(
                      labelText: 'Project brief',
                      hintText: 'What would you like to create together?',
                    ),
                  ),
                  if (error != null)
                    Text(error!, style: const TextStyle(color: Colors.amber)),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: busy ? null : () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: busy
                  ? null
                  : () async {
                      if (task.text.trim().isEmpty) {
                        update(
                          () => error = 'Add a short description of the work.',
                        );
                        return;
                      }
                      update(() {
                        busy = true;
                        error = null;
                      });
                      try {
                        if (employee) {
                          await _api.assignHumanTask(
                            employeeId: person['id'] as String,
                            sessionId: _sessionId,
                            description: task.text.trim(),
                          );
                        } else {
                          await _api.saveTalentBrief(
                            person['id'] as String,
                            _sessionId,
                            task.text.trim(),
                          );
                        }
                        if (!context.mounted) return;
                        Navigator.pop(context);
                        if (mounted) {
                          ScaffoldMessenger.of(this.context).showSnackBar(
                            const SnackBar(
                              content: Text(
                                'Brief saved to your project. No message was sent.',
                              ),
                            ),
                          );
                        }
                      } catch (_) {
                        if (context.mounted) {
                          update(() {
                            busy = false;
                            error =
                                'Could not save the brief. Please check your connection and retry.';
                          });
                        }
                      }
                    },
              child: Text(busy ? 'Saving…' : 'Save project brief'),
            ),
          ],
        ),
      ),
    );
    // Dialog transitions can still reference the field during their exit frame.
    await Future<void>.delayed(const Duration(milliseconds: 250));
    task.dispose();
  }

  String _availability(Map<String, dynamic> p) => p['is_example'] == true
      ? 'Example profile · Not available for hire'
      : switch (p['availability']) {
          'limited' => 'Limited availability',
          'unavailable' => 'Not taking new work',
          _ => 'Available for work',
        };

  Widget _landing(double width) => MarketWorkPicker(
    onDepartment: (id) => setState(() {
      _department = id;
      _kind = null;
      _error = null;
    }),
    onAllModels: () => _open('ai'),
    onEmployee: _addEmployee,
    onOffer: _editProfile,
  );

  Widget _choosePeople() => MarketSupplierPicker(
    department: marketDepartment(_department)!,
    onChoose: _open,
    onEmployee: _addEmployee,
  );

  Widget _humanDirectory() {
    final query = _search.text.trim().toLowerCase();
    final own = _kind == 'employee';
    final items = own ? _employees : _people;
    final people = items
        .where(
          (p) =>
              _department == null ||
              p['department'] == null ||
              p['department'] == 'general' ||
              p['department'] == _department,
        )
        .where(
          (p) =>
              '${p['name']} ${p['role']} ${p['summary']} ${(p['skills'] as List? ?? []).join(' ')}'
                  .toLowerCase()
                  .contains(query),
        )
        .where((p) => !_availableOnly || p['availability'] == 'available')
        .toList();
    if (_sortByRate) {
      people.sort(
        (a, b) =>
            ((a['rate'] as num?) ?? 0).compareTo((b['rate'] as num?) ?? 0),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          own ? 'People you already trust.' : 'People make\nthe difference.',
          style: TextStyle(
            fontSize: 40,
            height: 1.12,
            fontWeight: FontWeight.w600,
            letterSpacing: -1,
          ),
        ),
        const SizedBox(height: 16),
        Text(
          own
              ? 'Your private team for this project. Add employees you already work with, record their skills, and prepare their tasks.'
              : 'Independent talent, in their own words. Find someone who cares about the work as much as you do.',
          style: TextStyle(color: Colors.white60, height: 1.6),
        ),
        const SizedBox(height: 24),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: arcLilac,
                foregroundColor: Colors.black,
              ),
              onPressed: own ? _addEmployee : _editProfile,
              icon: const Icon(Icons.person_add_alt_1),
              label: Text(
                own
                    ? 'Add my employee'
                    : _myProfile == null
                    ? 'Offer your skills'
                    : 'Manage my profile',
              ),
            ),
            FilterChip(
              label: const Text('Available now'),
              selected: _availableOnly,
              onSelected: (v) => setState(() => _availableOnly = v),
            ),
            FilterChip(
              label: const Text('Lowest rate first'),
              selected: _sortByRate,
              onSelected: (v) => setState(() => _sortByRate = v),
            ),
          ],
        ),
        const SizedBox(height: 22),
        TextField(
          controller: _search,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            hintText: 'Find a person, skill, or specialty',
            prefixIcon: const Icon(Icons.search),
            filled: true,
            fillColor: arcPanel,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(18),
              borderSide: BorderSide.none,
            ),
          ),
        ),
        const SizedBox(height: 24),
        if (_loading) const LinearProgressIndicator(color: arcLilac),
        if (_error != null) ArcNotice(message: _error!, onRetry: _load),
        if (!_loading && _error == null && people.isEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(34),
            decoration: BoxDecoration(
              color: arcPanel,
              borderRadius: BorderRadius.circular(24),
            ),
            child: Column(
              children: [
                const Icon(Icons.spa_outlined, size: 40, color: arcLilac),
                const SizedBox(height: 16),
                Text(
                  items.isEmpty
                      ? own
                            ? 'Bring your people into the project.'
                            : 'The next great collaborator could be you.'
                      : 'No matches just yet.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 22),
                ),
                const SizedBox(height: 12),
                Text(
                  items.isEmpty
                      ? own
                            ? 'Add an employee to record their role, skills, availability, and rate.'
                            : 'Be the first to introduce your craft to the collective.'
                      : 'Try another skill or change your availability filter.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white60),
                ),
              ],
            ),
          ),
        LayoutBuilder(
          builder: (context, bounds) {
            final columns = bounds.maxWidth > 1000
                ? 3
                : bounds.maxWidth > 620
                ? 2
                : 1;
            final cardWidth = (bounds.maxWidth - (columns - 1) * 16) / columns;
            return Wrap(
              spacing: 16,
              runSpacing: 16,
              children: people
                  .map(
                    (p) => SizedBox(
                      width: cardWidth,
                      child: Material(
                        color: arcPanel,
                        borderRadius: BorderRadius.circular(24),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(24),
                          onTap: () => _viewPerson(p, employee: own),
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    CircleAvatar(
                                      radius: 25,
                                      backgroundColor: arcLilac.withValues(
                                        alpha: .18,
                                      ),
                                      child: Text(
                                        (p['name'] as String).characters.first
                                            .toUpperCase(),
                                        style: const TextStyle(
                                          color: arcLilac,
                                          fontSize: 22,
                                        ),
                                      ),
                                    ),
                                    const Spacer(),
                                    if (p['is_example'] == true)
                                      const Chip(label: Text('Example'))
                                    else if (p['is_mine'] == true)
                                      const Chip(label: Text('You'))
                                    else
                                      const Icon(
                                        Icons.north_east,
                                        size: 20,
                                        color: Colors.white54,
                                      ),
                                  ],
                                ),
                                const SizedBox(height: 20),
                                Text(
                                  p['name'] as String,
                                  style: const TextStyle(
                                    fontSize: 23,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  p['role'] as String,
                                  style: const TextStyle(color: arcLilac),
                                ),
                                const SizedBox(height: 14),
                                Text(
                                  p['summary'] as String,
                                  maxLines: 3,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: Colors.white60,
                                    height: 1.6,
                                  ),
                                ),
                                const SizedBox(height: 14),
                                Wrap(
                                  spacing: 6,
                                  runSpacing: 6,
                                  children: (p['skills'] as List? ?? [])
                                      .take(3)
                                      .map(
                                        (s) => Chip(
                                          label: Text(
                                            '$s',
                                            style: const TextStyle(
                                              fontSize: 11,
                                            ),
                                          ),
                                        ),
                                      )
                                      .toList(),
                                ),
                                const SizedBox(height: 18),
                                Text(
                                  talentPrice(p),
                                  style: const TextStyle(
                                    fontSize: 19,
                                    color: arcLime,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  _availability(p),
                                  style: TextStyle(
                                    color: p['availability'] == 'available'
                                        ? arcLime
                                        : Colors.white54,
                                    fontSize: 12,
                                  ),
                                ),
                                if (p['is_example'] != true) ...[
                                  const SizedBox(height: 8),
                                  Text(
                                    '${p['remaining_capacity'] ?? p['job_capacity'] ?? 3} / ${p['job_capacity'] ?? 3} job slots open',
                                    style: const TextStyle(
                                      color: arcLilac,
                                      fontSize: 12,
                                    ),
                                  ),
                                ],
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
      ],
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: arcCanvas,
    appBar: AppBar(
      backgroundColor: arcCanvas,
      surfaceTintColor: Colors.transparent,
      title: const Text('The collective', style: TextStyle(fontSize: 18)),
      actions: [
        if (_kind != null || _department != null)
          TextButton.icon(
            onPressed: () => setState(() {
              _kind = null;
              _department = null;
              _error = null;
            }),
            icon: const Icon(Icons.grid_view_rounded, size: 17),
            label: const Text('Explore'),
          ),
        const SizedBox(width: 12),
      ],
    ),
    body: Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1200),
        child: LayoutBuilder(
          builder: (context, bounds) => SingleChildScrollView(
            key: ValueKey('$_department:$_kind'),
            padding: EdgeInsets.fromLTRB(
              bounds.maxWidth < 650 ? 20 : 44,
              30,
              bounds.maxWidth < 650 ? 20 : 44,
              48,
            ),
            child: _kind == null
                ? _department == null
                      ? _landing(bounds.maxWidth)
                      : _choosePeople()
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(bottom: 26),
                        child: Wrap(
                          spacing: 10,
                          runSpacing: 8,
                          children: [
                            ChoiceChip(
                              label: const Text('AI models'),
                              selected: _kind == 'ai',
                              onSelected: (_) => _open('ai'),
                            ),
                            ChoiceChip(
                              label: const Text('Human talent'),
                              selected: _kind == 'human',
                              onSelected: (_) => _open('human'),
                            ),
                            ChoiceChip(
                              label: const Text('Your employees'),
                              selected: _kind == 'employee',
                              onSelected: (_) => _open('employee'),
                            ),
                            if (_department != null)
                              ActionChip(
                                label: Text(
                                  marketDepartment(_department)!.name,
                                ),
                                onPressed: () => setState(() {
                                  _department = null;
                                  _kind = null;
                                }),
                              ),
                          ],
                        ),
                      ),
                      if (_kind == 'ai')
                        ProjectTeamMarket(
                          key: ValueKey('ai-directory:$_department'),
                          api: _api,
                          sessionId: _sessionId,
                          roles: _roles,
                          department: _department,
                        )
                      else
                        _humanDirectory(),
                    ],
                  ),
          ),
        ),
      ),
    ),
  );
}
