import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:arc/frontend/arc_design.dart';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/talent_profile_editor.dart';
import 'package:arc/frontend/work_api.dart';

class WorkBoard extends StatefulWidget {
  const WorkBoard({super.key, required this.sessionId, this.api});
  final String sessionId;
  final WorkApi? api;
  @override
  State<WorkBoard> createState() => _WorkBoardState();
}

class _WorkBoardState extends State<WorkBoard> {
  late final WorkApi api = widget.api ?? WorkApi();
  Map<String, dynamic> board = {};
  Timer? timer;
  String? error, model;
  bool fetching = false, busy = false, automatic = false, paidConfirmed = false;
  String get path =>
      '/company/sessions/${Uri.encodeComponent(widget.sessionId)}/work';
  List<Map<String, dynamic>> items(String key) => ((board[key] as List?) ?? [])
      .map((e) => Map<String, dynamic>.from(e as Map))
      .toList();
  @override
  void initState() {
    super.initState();
    load(refresh: true);
    timer = Timer.periodic(const Duration(seconds: 5), (_) => load());
  }

  Future<void> load({bool refresh = false}) async {
    if (fetching) return;
    fetching = true;
    try {
      final result = await api.request(
        '$path${refresh ? '?refresh=true' : ''}',
      );
      if (mounted) {
        setState(() {
          board = result;
          error = null;
          final models = items('models');
          final saved = result['model'] as String?;
          if (result['enabled'] == true ||
              result['enabled'] == 1 ||
              model == null) {
            model = saved?.isNotEmpty == true ? saved : null;
          }
          if (model != null &&
              !models.any((m) => m['model_id'] == model) &&
              result['enabled'] != true &&
              result['enabled'] != 1) {
            model = null;
            paidConfirmed = false;
          }
        });
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => error =
              'The work board is unavailable. Your queued work stays saved; try again.',
        );
      }
    } finally {
      fetching = false;
    }
  }

  @override
  void dispose() {
    timer?.cancel();
    if (widget.api == null) api.close();
    super.dispose();
  }

  Future<void> change(bool enabled) async {
    setState(() => busy = true);
    try {
      await api.request(
        path,
        method: 'PUT',
        body: {
          'enabled': enabled,
          'model': model ?? '',
          'confirm_local_autonomy': automatic,
          'confirm_paid_model': paidConfirmed,
        },
      );
      await load();
    } catch (_) {
      if (mounted) {
        setState(
          () => error =
              'Choose a model, confirm its pricing if needed, and allow local project work before starting.',
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> addEmployee() async {
    final people = CompanyApiClient();
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => TalentProfileEditor(
          api: people,
          employee: true,
          sessionId: widget.sessionId,
        ),
      ),
    );
    people.close();
    await load();
  }

  Future<void> ownedDialog(WidgetBuilder builder) async {
    final route = DialogRoute<void>(context: context, builder: builder);
    await Navigator.of(context).push(route);
    await route.completed;
  }

  Future<void> newTask() async {
    final title = TextEditingController(),
        description = TextEditingController();
    String kind = 'agent', assignee = 'ceo', manager = 'ceo';
    final availablePeople = items('employees')
        .where(
          (e) =>
              (e['remaining_capacity'] as num? ??
                  e['job_capacity'] as num? ??
                  3) >
              0,
        )
        .toList();
    bool verify = false, saving = false;
    String? failure;
    await ownedDialog(
      (dialog) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          backgroundColor: arcPanel,
          title: const Text('Give your company a task'),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(
                        value: 'agent',
                        label: Text('AI team'),
                        icon: Icon(Icons.auto_awesome),
                      ),
                      ButtonSegment(
                        value: 'human',
                        label: Text('Human'),
                        icon: Icon(Icons.person_outline),
                      ),
                    ],
                    selected: {kind},
                    onSelectionChanged: (v) => update(() {
                      kind = v.first;
                      assignee = kind == 'agent'
                          ? 'ceo'
                          : availablePeople.isEmpty
                          ? ''
                          : availablePeople.first['id'] as String;
                    }),
                  ),
                  const SizedBox(height: 18),
                  if (kind == 'agent')
                    const Text(
                      'The CEO will make a plan and choose the team if you haven’t chosen one.',
                      style: TextStyle(color: Colors.white60),
                    ),
                  if (kind == 'human' && items('employees').isNotEmpty)
                    DropdownButtonFormField<String>(
                      initialValue: assignee.isEmpty ? null : assignee,
                      decoration: const InputDecoration(labelText: 'Assign to'),
                      items: items('employees')
                          .map(
                            (e) => DropdownMenuItem(
                              value: e['id'] as String,
                              enabled:
                                  (e['remaining_capacity'] as num? ??
                                      e['job_capacity'] as num? ??
                                      3) >
                                  0,
                              child: Text(
                                "${e['name']} · ${e['remaining_capacity'] ?? e['job_capacity'] ?? 3} slots open",
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (v) => assignee = v!,
                    ),
                  if (kind == 'human')
                    DropdownButtonFormField<String>(
                      initialValue: manager,
                      decoration: const InputDecoration(
                        labelText: 'Reports to',
                      ),
                      items:
                          (items('managers').isEmpty
                                  ? <Map<String, dynamic>>[
                                      {'id': 'ceo', 'name': 'Company CEO'},
                                    ]
                                  : items('managers'))
                              .map(
                                (m) => DropdownMenuItem(
                                  value: m['id'] as String,
                                  child: Text(m['name'] as String),
                                ),
                              )
                              .toList(),
                      onChanged: (v) => manager = v!,
                    ),
                  if (kind == 'human' && items('employees').isEmpty)
                    const Text(
                      'Add an employee first. Their private work link opens only their assignments.',
                    ),
                  TextField(
                    controller: title,
                    maxLength: 140,
                    decoration: const InputDecoration(
                      labelText: 'What needs doing?',
                    ),
                  ),
                  TextField(
                    controller: description,
                    minLines: 4,
                    maxLines: 8,
                    maxLength: 8000,
                    decoration: const InputDecoration(
                      labelText: 'Brief and acceptance criteria',
                      hintText:
                          'Describe the outcome, relevant files, and how to check the result.',
                    ),
                  ),
                  if (kind == 'agent')
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Require a passing terminal check'),
                      subtitle: const Text(
                        'Useful for code fixes and implementation work.',
                      ),
                      value: verify,
                      onChanged: (v) => update(() => verify = v!),
                    ),
                  if (kind == 'human')
                    const Text(
                      'The person accepts the offer, submits work privately, and receives a review from the CEO. Paid terms must be agreed separately.',
                      style: TextStyle(color: Colors.white60, height: 1.5),
                    ),
                  if (failure != null)
                    Text(
                      failure!,
                      style: const TextStyle(color: Colors.orangeAccent),
                    ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: saving ? null : () => Navigator.pop(dialog),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: saving || assignee.isEmpty
                  ? null
                  : () async {
                      if (title.text.trim().isEmpty ||
                          description.text.trim().isEmpty) {
                        update(
                          () => failure = 'Add a title and a clear brief.',
                        );
                        return;
                      }
                      update(() => saving = true);
                      try {
                        await api.request(
                          '$path/tasks',
                          method: 'POST',
                          body: {
                            'title': title.text.trim(),
                            'description': description.text.trim(),
                            'kind': kind,
                            'assignee': assignee,
                            'manager': manager,
                            'requires_check': verify && kind == 'agent',
                          },
                        );
                        if (dialog.mounted) Navigator.pop(dialog);
                      } catch (_) {
                        update(() {
                          failure = 'We couldn’t save this task. Try again.';
                          saving = false;
                        });
                      }
                    },
              child: Text(saving ? 'Saving…' : 'Add task'),
            ),
          ],
        ),
      ),
    );
    title.dispose();
    description.dispose();
    await load();
  }

  Future<void> invite(Map<String, dynamic> person) async {
    try {
      final data = await api.request(
        '$path/invites/${person['id']}',
        method: 'POST',
        body: {},
      );
      final link = Uri.base
          .replace(
            queryParameters: {'view': 'work'},
            fragment: Uri(
              queryParameters: {'invite': data['token'] as String},
            ).query,
          )
          .toString();
      if (!mounted) return;
      await ownedDialog(
        (dialog) => AlertDialog(
          backgroundColor: arcPanel,
          title: Text('Private work link for ${person['name']}'),
          content: SizedBox(
            width: 460,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'This link opens only this person’s tasks. It expires in 7 days. Share it directly with them; creating a new link revokes the old one.',
                ),
                const SizedBox(height: 16),
                SelectableText(link),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialog),
              child: const Text('Close'),
            ),
            FilledButton.icon(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: link));
                if (dialog.mounted) Navigator.pop(dialog);
              },
              icon: const Icon(Icons.copy),
              label: const Text('Copy private link'),
            ),
          ],
        ),
      );
    } catch (_) {
      if (mounted) {
        setState(
          () => error = 'We couldn’t prepare that work link. Try again.',
        );
      }
    }
  }

  Future<void> detail(Map<String, dynamic> task) async {
    final feedback = TextEditingController();
    await ownedDialog(
      (dialog) => AlertDialog(
        backgroundColor: arcPanel,
        title: Text(task['title'] as String),
        content: SizedBox(
          width: 600,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  task['description'] as String,
                  style: const TextStyle(height: 1.6),
                ),
                const SizedBox(height: 18),
                if ('${task['result']}'.isNotEmpty)
                  SelectableText(task['result'] as String),
                if ('${task['feedback']}'.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(
                    task['feedback'] as String,
                    style: const TextStyle(color: arcLilac, height: 1.5),
                  ),
                ],
                if (task['kind'] == 'human' && task['status'] == 'submitted')
                  TextField(
                    controller: feedback,
                    maxLines: 4,
                    maxLength: 8000,
                    decoration: const InputDecoration(
                      labelText: 'Review feedback',
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog),
            child: const Text('Close'),
          ),
          if (task['status'] == 'blocked')
            FilledButton(
              onPressed: () async {
                await api.request(
                  '$path/tasks/${task['id']}/retry',
                  method: 'POST',
                  body: {},
                );
                if (dialog.mounted) Navigator.pop(dialog);
              },
              child: const Text('Retry task'),
            ),
          if (task['kind'] == 'human' && task['status'] == 'submitted')
            ...['changes_requested', 'accepted'].map(
              (decision) => TextButton(
                onPressed: () async {
                  await api.request(
                    '$path/tasks/${task['id']}/review',
                    method: 'POST',
                    body: {'decision': decision, 'feedback': feedback.text},
                  );
                  if (dialog.mounted) Navigator.pop(dialog);
                },
                child: Text(
                  decision == 'accepted' ? 'Accept work' : 'Request changes',
                ),
              ),
            ),
        ],
      ),
    );
    feedback.dispose();
    await load();
  }

  @override
  Widget build(BuildContext context) {
    final enabled = board['enabled'] == true || board['enabled'] == 1;
    final models = items('models'),
        tasks = items('tasks'),
        people = items('employees');
    final selectedModel = models
        .where((m) => m['model_id'] == model)
        .firstOrNull;
    final paidModel =
        selectedModel != null &&
        ((selectedModel['input_price_per_million'] as num? ?? 0) > 0 ||
            (selectedModel['output_price_per_million'] as num? ?? 0) > 0);
    return Scaffold(
      backgroundColor: arcCanvas,
      appBar: AppBar(
        backgroundColor: arcCanvas,
        title: const Text('Company work'),
        actions: [
          IconButton(
            onPressed: () => load(refresh: true),
            tooltip: 'Refresh work',
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1080),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const Text(
                'Your team.\nWork on schedule.',
                style: TextStyle(
                  fontSize: 38,
                  fontWeight: FontWeight.w600,
                  height: 1.15,
                  letterSpacing: -1,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'A simple scheduler checks jobs every 5 seconds and wakes assigned agents only when work is ready. Reminders use no AI calls.',
                style: TextStyle(color: Colors.white60, height: 1.6),
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  color: arcPanel,
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Icon(
                          enabled
                              ? Icons.play_circle_outline
                              : Icons.pause_circle_outline,
                          color: arcLime,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            enabled
                                ? 'Scheduler is running'
                                : 'Scheduler is paused',
                            style: const TextStyle(
                              fontSize: 19,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        Text(
                          'SCHEDULER',
                          style: TextStyle(
                            color: arcLime,
                            fontSize: 11,
                            letterSpacing: 1.4,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    if (models.isNotEmpty)
                      DropdownButtonFormField<String>(
                        key: ValueKey(model),
                        initialValue: models.any((m) => m['model_id'] == model)
                            ? model
                            : null,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Planning & review model',
                        ),
                        items: models
                            .map(
                              (m) => DropdownMenuItem(
                                value: m['model_id'] as String,
                                child: Text(
                                  m['name'] as String,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            )
                            .toList(),
                        onChanged: enabled
                            ? null
                            : (v) => setState(() {
                                model = v;
                                paidConfirmed = false;
                              }),
                      ),
                    const SizedBox(height: 10),
                    const Text(
                      'This AI helps plan work and review submissions. The scheduler itself is an algorithm, not an AI agent.',
                      style: TextStyle(color: Colors.white60, fontSize: 12),
                    ),
                    if (selectedModel != null) ...[
                      const SizedBox(height: 10),
                      Text(
                        selectedModel['developer_connection'] == true
                            ? 'Your connection · usage is billed by your provider; local models run on your computer.'
                            : 'Provider pricing · USD per 1M tokens: \$${selectedModel['input_price_per_million']} input · \$${selectedModel['output_price_per_million']} output',
                        style: const TextStyle(color: arcLilac, fontSize: 12),
                      ),
                    ],
                    if (!enabled && paidModel)
                      Material(
                        color: Colors.transparent,
                        child: CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          value: paidConfirmed,
                          onChanged: (v) => setState(() => paidConfirmed = v!),
                          title: const Text(
                            'I agree to this model’s usage charges',
                          ),
                          subtitle: const Text(
                            'Automatic work can use this model and models with equal or lower input/output token rates. The daily request limit is not a dollar spending limit. Higher rates require a new confirmation.',
                          ),
                        ),
                      ),
                    if (!enabled)
                      OutlinedButton.icon(
                        onPressed:
                            busy ||
                                model == null ||
                                (paidModel && !paidConfirmed)
                            ? null
                            : () => change(false),
                        icon: const Icon(Icons.save_outlined),
                        label: const Text('Save model choice'),
                      ),
                    const SizedBox(height: 12),
                    const Text(
                      'Idle checks use no model requests. Automatic work is limited to 36 model requests per day. Provider charges and usage limits depend on your chosen model.',
                      style: TextStyle(
                        color: Colors.white54,
                        fontSize: 12,
                        height: 1.5,
                      ),
                    ),
                    if (!enabled)
                      Material(
                        color: Colors.transparent,
                        child: CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          value: automatic,
                          onChanged: (v) => setState(() => automatic = v!),
                          title: const Text(
                            'Allow automatic local project work',
                          ),
                          subtitle: const Text(
                            'Agents may read and update project files and run restricted local checks.',
                          ),
                        ),
                      ),
                    const SizedBox(height: 14),
                    FilledButton.icon(
                      onPressed:
                          busy ||
                              (!enabled &&
                                  (!automatic ||
                                      model == null ||
                                      (paidModel && !paidConfirmed)))
                          ? null
                          : () => change(!enabled),
                      icon: Icon(enabled ? Icons.pause : Icons.play_arrow),
                      label: Text(
                        busy
                            ? 'Saving…'
                            : enabled
                            ? 'Pause company work'
                            : 'Start company work',
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              if (error != null)
                ArcNotice(message: error!, onRetry: () => load(refresh: true)),
              Wrap(
                spacing: 12,
                runSpacing: 10,
                children: [
                  FilledButton.icon(
                    onPressed: newTask,
                    icon: const Icon(Icons.add_task),
                    label: const Text('Add work'),
                  ),
                  OutlinedButton.icon(
                    onPressed: addEmployee,
                    icon: const Icon(Icons.person_add_alt_1),
                    label: const Text('Add my employee'),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              if (tasks.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 32),
                  child: Text(
                    'Nothing queued. Your team stays quiet until there’s work to do.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white54, height: 1.6),
                  ),
                ),
              ...tasks.map(
                (task) => Card(
                  color: arcPanel,
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    contentPadding: const EdgeInsets.all(18),
                    leading: Icon(
                      task['kind'] == 'human'
                          ? Icons.person_outline
                          : task['kind'] == 'review'
                          ? Icons.rate_review_outlined
                          : Icons.auto_awesome,
                      color: arcLilac,
                    ),
                    title: Text(task['title'] as String),
                    subtitle: Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        '${(task['status'] as String).replaceAll('_', ' ')} · ${task['kind'] == 'human' ? 'Reviewed by ${task['manager']}' : task['assignee']}',
                        style: const TextStyle(color: Colors.white60),
                      ),
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => detail(task),
                  ),
                ),
              ),
              if (people.isNotEmpty) ...[
                const SizedBox(height: 24),
                const Text(
                  'Private human workspaces',
                  style: TextStyle(fontSize: 21, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                ...people.map(
                  (p) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.badge_outlined, color: arcLilac),
                    title: Text(p['name'] as String),
                    subtitle: Text(
                      '${p['role']}\n${p['remaining_capacity'] ?? p['job_capacity'] ?? 3} / ${p['job_capacity'] ?? 3} job slots open',
                    ),
                    isThreeLine: true,
                    trailing: Wrap(
                      children: [
                        IconButton(
                          tooltip: 'Revoke work link',
                          icon: const Icon(Icons.link_off),
                          onPressed: () async {
                            await api.request(
                              '$path/invites/${p['id']}',
                              method: 'DELETE',
                            );
                          },
                        ),
                        TextButton(
                          onPressed: () => invite(p),
                          child: const Text('Private work link'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
