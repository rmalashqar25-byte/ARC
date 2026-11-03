import 'dart:async';
import 'package:flutter/material.dart';
import 'package:arc/frontend/arc_design.dart';
import 'package:arc/frontend/work_api.dart';

class HumanWorkPortal extends StatefulWidget {
  const HumanWorkPortal({super.key, required this.invitation, this.api});
  final String invitation;
  final WorkApi? api;
  @override
  State<HumanWorkPortal> createState() => _HumanWorkPortalState();
}

class _HumanWorkPortalState extends State<HumanWorkPortal> {
  late final WorkApi api =
      widget.api ?? WorkApi(workerToken: widget.invitation);
  Timer? timer;
  Map<String, dynamic> data = {};
  String? error;
  bool fetching = false;
  @override
  void initState() {
    super.initState();
    load();
    timer = Timer.periodic(const Duration(seconds: 5), (_) => load());
  }

  Future<void> load() async {
    if (fetching) return;
    fetching = true;
    try {
      final result = await api.request('/work/tasks');
      if (mounted) {
        setState(() {
          data = result;
          error = null;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => error =
              'This work link is unavailable or expired. Ask your manager for a new private invitation.',
        );
      }
    } finally {
      fetching = false;
    }
  }

  Future<void> action(String id, String action, {String? content}) async {
    await api.request(
      '/work/tasks/${Uri.encodeComponent(id)}/$action',
      method: 'POST',
      body: content == null ? {} : {'content': content},
    );
    await load();
  }

  @override
  void dispose() {
    timer?.cancel();
    if (widget.api == null) api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tasks = (data['tasks'] as List?) ?? [];
    final person = (data['person'] as Map?) ?? {};
    final groups = (data['groups'] as List?) ?? [];
    return Scaffold(
      backgroundColor: arcCanvas,
      appBar: AppBar(
        backgroundColor: arcCanvas,
        automaticallyImplyLeading: false,
        title: const Text('ARC · Your work'),
        actions: [
          IconButton(
            onPressed: load,
            tooltip: 'Refresh my jobs',
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 880),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const Text(
                'Your craft.\nYour next contribution.',
                style: TextStyle(
                  fontSize: 36,
                  fontWeight: FontWeight.w600,
                  height: 1.15,
                  letterSpacing: -1,
                ),
              ),
              const SizedBox(height: 14),
              Text(
                person['name'] == null
                    ? 'Your private job workspace.'
                    : 'Welcome, ${person['name']}. ${person['active_jobs'] ?? 0} / ${person['job_capacity'] ?? 3} job slots in use.',
                style: const TextStyle(color: arcLilac, height: 1.6),
              ),
              const SizedBox(height: 10),
              const Text(
                'See your brief, accept a job, and submit your work to your manager. This workspace contains only your assigned jobs and review feedback.',
                style: TextStyle(color: Colors.white60, height: 1.6),
              ),
              ...groups.map(
                (g) => Padding(
                  padding: const EdgeInsets.only(top: 14),
                  child: Chip(
                    avatar: const Icon(Icons.workspaces_outline, size: 18),
                    label: Text(
                      '${(g as Map)['name']} · Manager: ${g['manager_name']}',
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 24),
              if (error != null) ArcNotice(message: error!, onRetry: load),
              if (error == null && data.isEmpty)
                const LinearProgressIndicator(),
              if (error == null && data.isNotEmpty && tasks.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 35),
                  child: Text(
                    'No jobs assigned yet. Your manager’s next offer will appear here.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white60),
                  ),
                ),
              ...tasks.map(
                (t) => _HumanJob(
                  key: ValueKey((t as Map)['id']),
                  task: Map<String, dynamic>.from(t),
                  onAction: action,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HumanJob extends StatefulWidget {
  const _HumanJob({super.key, required this.task, required this.onAction});
  final Map<String, dynamic> task;
  final Future<void> Function(String, String, {String? content}) onAction;
  @override
  State<_HumanJob> createState() => _HumanJobState();
}

class _HumanJobState extends State<_HumanJob> {
  late final TextEditingController result = TextEditingController(
    text: widget.task['result'] as String? ?? '',
  );
  bool busy = false;
  String? error;
  Future<void> send(String action) async {
    if (action == 'submit' && result.text.trim().isEmpty) {
      setState(
        () => error = 'Add the finished work or a deliverable link first.',
      );
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.onAction(
        widget.task['id'] as String,
        action,
        content: action == 'submit' ? result.text.trim() : null,
      );
    } catch (_) {
      if (mounted) {
        setState(
          () => error =
              'This job changed or the connection was interrupted. Refresh and try again.',
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    result.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final task = widget.task, status = task['status'] as String;
    final working = status == 'in_progress' || status == 'changes_requested';
    return Card(
      color: arcPanel,
      margin: const EdgeInsets.only(bottom: 18),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              spacing: 10,
              runSpacing: 8,
              children: [
                Text(
                  status.replaceAll('_', ' ').toUpperCase(),
                  style: const TextStyle(
                    color: arcLime,
                    fontSize: 11,
                    letterSpacing: 1.2,
                  ),
                ),
                Text(
                  'Manager: ${task['manager']}',
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              task['title'] as String,
              style: const TextStyle(fontSize: 23, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 14),
            SelectableText(
              task['description'] as String,
              style: const TextStyle(height: 1.6, color: Colors.white70),
            ),
            if ((task['feedback'] as String? ?? '').isNotEmpty) ...[
              const SizedBox(height: 18),
              const Text(
                'Manager feedback',
                style: TextStyle(color: arcLilac, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Text(
                task['feedback'] as String,
                style: const TextStyle(height: 1.6),
              ),
            ],
            if (working) ...[
              const SizedBox(height: 20),
              TextField(
                controller: result,
                minLines: 6,
                maxLines: 18,
                maxLength: 20000,
                decoration: const InputDecoration(
                  labelText: 'Your deliverable',
                  hintText:
                      'Write your completed work, code, evidence, or a link to the result.',
                  alignLabelWithHint: true,
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: busy ? null : () => send('submit'),
                icon: const Icon(Icons.task_alt),
                label: Text(busy ? 'Sending…' : 'Submit work to manager'),
              ),
            ],
            if (!working && (task['result'] as String? ?? '').isNotEmpty) ...[
              const SizedBox(height: 18),
              const Text(
                'Your submitted work',
                style: TextStyle(color: arcLilac),
              ),
              const SizedBox(height: 8),
              SelectableText(
                task['result'] as String,
                style: const TextStyle(height: 1.6),
              ),
            ],
            if (status == 'offered') ...[
              const SizedBox(height: 18),
              const Text(
                'Accept only when the scope, availability, and any paid terms are agreed.',
                style: TextStyle(
                  color: Colors.white54,
                  fontSize: 12,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                children: [
                  FilledButton(
                    onPressed: busy ? null : () => send('accept'),
                    child: const Text('Accept job'),
                  ),
                  TextButton(
                    onPressed: busy ? null : () => send('decline'),
                    child: const Text('Decline'),
                  ),
                ],
              ),
            ],
            if (status == 'submitted')
              const Padding(
                padding: EdgeInsets.only(top: 16),
                child: Text(
                  'Submitted. Your manager’s review will appear here.',
                  style: TextStyle(color: arcLime),
                ),
              ),
            if (error != null)
              Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
          ],
        ),
      ),
    );
  }
}
