import 'dart:async';

import 'package:arc/frontend/company_api_client.dart';
import 'package:flutter/material.dart';
import 'package:arc/frontend/arc_design.dart';

/// Read-only live feed shared by the AI screen and Company workspace.
class CompanyLiveActivity extends StatefulWidget {
  const CompanyLiveActivity({
    super.key,
    required this.api,
    required this.sessionId,
    this.onClose,
    this.initialGroupId,
  });
  final CompanyApiClient api;
  final String sessionId;
  final String? initialGroupId;
  final VoidCallback? onClose;
  @override
  State<CompanyLiveActivity> createState() => _CompanyLiveActivityState();
}

class _CompanyLiveActivityState extends State<CompanyLiveActivity> {
  final Map<int, CompanyEvent> _events = {};
  StreamSubscription<CompanyEvent>? _subscription;
  Timer? _retry;
  List<CompanyGroup> _groups = const [];
  bool _loading = true;
  bool _connected = false;
  String? _error;
  String? _selectedGroupId;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _selectedGroupId = widget.initialGroupId;
    _load();
  }

  @override
  void didUpdateWidget(covariant CompanyLiveActivity oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.sessionId != widget.sessionId ||
        oldWidget.api != widget.api) {
      _subscription?.cancel();
      _retry?.cancel();
      _generation++;
      _connected = false;
      _error = null;
      _selectedGroupId = widget.initialGroupId;
      _events.clear();
      _groups = const [];
      _loading = true;
      _load();
    }
  }

  Future<void> _load() async {
    final generation = _generation;
    try {
      final result = await Future.wait<Object>([
        widget.api.loadGroups(widget.sessionId),
        widget.api.loadEvents(widget.sessionId),
      ]);
      if (!mounted || generation != _generation) return;
      setState(() {
        _groups = result[0] as List<CompanyGroup>;
        for (final event in (result[1] as CompanyEventsPage).events) {
          _events[event.id] = event;
        }
        _loading = false;
        _error = null;
      });
      _listen();
    } catch (error) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _loading = false;
        _connected = false;
        _error = 'The company feed is unavailable.';
      });
      _scheduleRetry();
    }
  }

  void _listen() {
    final generation = _generation;
    _subscription?.cancel();
    final lastId = _events.keys.fold<int>(0, (a, b) => a > b ? a : b);
    _subscription = widget.api
        .watchEvents(widget.sessionId, afterId: lastId)
        .listen(
          (event) {
            if (!mounted || generation != _generation) return;
            setState(() {
              _events[event.id] = event;
              _connected = true;
              _error = null;
            });
            if (event.type == 'group_created' || event.type == 'member_added') {
              _refreshGroups();
            }
          },
          onError: (Object error) {
            if (!mounted || generation != _generation) return;
            setState(() {
              _connected = false;
              _error = 'The live connection paused.';
            });
            _scheduleRetry();
          },
          onDone: () {
            if (!mounted || generation != _generation) return;
            setState(() {
              _connected = false;
              _error = 'The live connection paused.';
            });
            _scheduleRetry();
          },
        );
  }

  void _scheduleRetry() {
    _retry?.cancel();
    _retry = Timer(const Duration(seconds: 2), () {
      if (mounted) _load();
    });
  }

  void _retryNow() {
    _retry?.cancel();
    setState(() {
      _loading = true;
      _error = null;
    });
    _load();
  }

  Future<void> _refreshGroups() async {
    final generation = _generation;
    try {
      final groups = await widget.api.loadGroups(widget.sessionId);
      if (mounted && generation == _generation) {
        setState(() => _groups = groups);
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    _retry?.cancel();
    _subscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final allEvents = _events.values.toList()
      ..sort((a, b) => b.id.compareTo(a.id));
    final events = allEvents
        .where((e) => _selectedGroupId == null || e.groupId == _selectedGroupId)
        .toList();
    final status = _loading
        ? 'Connecting'
        : _connected
        ? 'Live'
        : _error != null
        ? allEvents.isEmpty
              ? 'Offline'
              : 'Reconnecting'
        : 'Ready';
    final statusColor = _error != null
        ? const Color(0xFFE5C68E)
        : _connected
        ? arcLime
        : arcLilac;
    return Container(
      margin: const EdgeInsets.fromLTRB(0, 8, 8, 8),
      decoration: BoxDecoration(
        color: arcCanvas,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFF2A3326)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: SafeArea(
          top: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 18, 10, 14),
                child: Row(
                  children: [
                    Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        color: arcLilac.withValues(alpha: .12),
                        borderRadius: BorderRadius.circular(13),
                      ),
                      child: const Icon(
                        Icons.hub_outlined,
                        color: arcLilac,
                        size: 21,
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Company activity',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: Color(0xFFE8EDE6),
                            ),
                          ),
                          SizedBox(height: 4),
                          Text(
                            'Your team, in motion',
                            style: TextStyle(
                              fontSize: 11,
                              color: Color(0xFF879481),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (widget.onClose != null)
                      IconButton(
                        tooltip: 'Close activity',
                        onPressed: widget.onClose,
                        icon: const Icon(
                          Icons.close_rounded,
                          size: 19,
                          color: Color(0xFF879481),
                        ),
                      ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 0, 18, 16),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: statusColor.withValues(alpha: .08),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: statusColor.withValues(alpha: .16),
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.circle, size: 6, color: statusColor),
                          const SizedBox(width: 7),
                          Text(
                            status,
                            style: TextStyle(
                              color: statusColor,
                              fontSize: 11,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const Spacer(),
                    const Icon(
                      Icons.visibility_outlined,
                      size: 13,
                      color: Color(0xFF788674),
                    ),
                    const SizedBox(width: 6),
                    const Text(
                      'Read-only',
                      style: TextStyle(fontSize: 10, color: Color(0xFF788674)),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1, color: Color(0xFF252E21)),
              if (_loading && allEvents.isEmpty)
                const Expanded(
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: arcLime,
                          ),
                        ),
                        SizedBox(height: 18),
                        Text(
                          'Connecting to your workspace',
                          style: TextStyle(
                            fontSize: 12,
                            color: Color(0xFF8C9885),
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              else if (allEvents.isEmpty && _groups.isEmpty)
                Expanded(
                  child: _ActivityEmpty(
                    offline: _error != null,
                    onRetry: _retryNow,
                  ),
                )
              else ...[
                if (_groups.isNotEmpty)
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
                    child: Row(
                      children: [
                        ChoiceChip(
                          label: const Text(
                            'All updates',
                            style: TextStyle(fontSize: 11),
                          ),
                          selected: _selectedGroupId == null,
                          onSelected: (_) =>
                              setState(() => _selectedGroupId = null),
                        ),
                        for (final group in _groups) ...[
                          const SizedBox(width: 8),
                          ChoiceChip(
                            label: ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 150),
                              child: Text(
                                group.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 11),
                              ),
                            ),
                            selected: _selectedGroupId == group.id,
                            onSelected: (_) =>
                                setState(() => _selectedGroupId = group.id),
                          ),
                        ],
                      ],
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
                  child: Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'LATEST UPDATES',
                          style: TextStyle(
                            color: Color(0xFF788674),
                            fontSize: 10,
                            letterSpacing: 1.5,
                          ),
                        ),
                      ),
                      Text(
                        '${events.length}',
                        style: const TextStyle(
                          color: Color(0xFF788674),
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    child: ArcNotice(
                      message:
                          'Connection paused. Your loaded updates are still here. We’ll keep trying.',
                      onRetry: _retryNow,
                    ),
                  ),
                Expanded(
                  child: events.isEmpty
                      ? const Center(
                          child: Padding(
                            padding: EdgeInsets.all(24),
                            child: Text(
                              'Updates for this team will appear here.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Color(0xFF8C9885),
                                height: 1.6,
                              ),
                            ),
                          ),
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          itemCount: events.length,
                          itemBuilder: (context, index) {
                            final event = events[index];
                            final room = _groups
                                .where((g) => g.id == event.groupId)
                                .firstOrNull;
                            return _ActivityEvent(
                              event: event,
                              groupName: room?.name,
                            );
                          },
                        ),
                ),
              ],
              const Divider(height: 1, color: Color(0xFF252E21)),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 18, vertical: 13),
                child: Row(
                  children: [
                    Icon(
                      Icons.chat_bubble_outline_rounded,
                      size: 13,
                      color: Color(0xFF788674),
                    ),
                    SizedBox(width: 9),
                    Expanded(
                      child: Text(
                        'Talk to your CEO in the main chat.',
                        style: TextStyle(
                          color: Color(0xFF788674),
                          fontSize: 11,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActivityEmpty extends StatelessWidget {
  const _ActivityEmpty({required this.offline, required this.onRetry});
  final bool offline;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, bounds) => SingleChildScrollView(
      padding: const EdgeInsets.all(22),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: bounds.maxHeight > 44 ? bounds.maxHeight - 44 : 0,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const ArcOrbit(size: 112),
            const SizedBox(height: 16),
            Text(
              offline
                  ? 'Let’s reconnect\nyour company.'
                  : 'A clear view\nof your team.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 24,
                height: 1.15,
                letterSpacing: -.6,
                fontWeight: FontWeight.w600,
                color: Color(0xFFE1EADB),
              ),
            ),
            const SizedBox(height: 14),
            Text(
              offline
                  ? 'Reconnect to see your company’s latest work. We’ll keep trying in the background.'
                  : 'When your CEO delegates, follow every handoff, team update, and report here.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 12,
                height: 1.7,
                color: Color(0xFF8C9885),
              ),
            ),
            const SizedBox(height: 22),
            if (offline)
              FilledButton.icon(
                onPressed: onRetry,
                style: FilledButton.styleFrom(
                  backgroundColor: arcLime,
                  foregroundColor: const Color(0xFF14200A),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 15,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                icon: const Icon(Icons.refresh_rounded, size: 17),
                label: const Text(
                  'Retry connection',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                ),
              )
            else
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: arcPanel,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFF293324)),
                ),
                child: const Column(
                  children: [
                    Text(
                      'FROM IDEA TO ACTION',
                      style: TextStyle(
                        color: arcLime,
                        fontSize: 9,
                        letterSpacing: 1.6,
                      ),
                    ),
                    SizedBox(height: 12),
                    Text(
                      'CEO brief  →  Team handoff  →  Progress',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 11,
                        color: Color(0xFFABB8A3),
                        height: 1.6,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

class _ActivityEvent extends StatelessWidget {
  const _ActivityEvent({required this.event, this.groupName});
  final CompanyEvent event;
  final String? groupName;
  @override
  Widget build(BuildContext context) {
    final (label, icon, color) = switch (event.type) {
      'user_message' => (
        'Founder brief',
        Icons.chat_bubble_outline_rounded,
        const Color(0xFFB6C1AE),
      ),
      'ceo_response' => ('CEO update', Icons.auto_awesome_outlined, arcLime),
      'task_delegated' => ('Task assigned', Icons.call_split_rounded, arcLilac),
      'agent_report' => (
        'Progress report',
        Icons.description_outlined,
        arcLime,
      ),
      'group_created' => (
        'Team formed',
        Icons.hub_outlined,
        const Color(0xFFFFD6A0),
      ),
      'member_added' => (
        'Teammate joined',
        Icons.person_add_alt_1_outlined,
        const Color(0xFFFFD6A0),
      ),
      _ => ('Team update', Icons.bolt_outlined, arcLilac),
    };
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: arcPanel,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF293324)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(7),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: .1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: color, size: 15),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    color: color,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (event.createdAt.millisecondsSinceEpoch > 0)
                Text(
                  TimeOfDay.fromDateTime(event.createdAt).format(context),
                  style: const TextStyle(
                    color: Color(0xFF788674),
                    fontSize: 10,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            '${_agentLabel(event.senderId)}${event.recipientId.isEmpty ? '' : '  →  ${_agentLabel(event.recipientId)}'}',
            style: const TextStyle(
              color: Color(0xFFE0E8DB),
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 10),
          SelectableText(
            event.content,
            style: const TextStyle(
              color: Color(0xFFABB8A3),
              fontSize: 13,
              height: 1.6,
            ),
          ),
          if (groupName != null) ...[
            const SizedBox(height: 12),
            Text(
              groupName!,
              style: const TextStyle(color: Color(0xFF788674), fontSize: 10),
            ),
          ],
        ],
      ),
    );
  }

  String _agentLabel(String id) {
    if (id == 'ceo') return 'CEO';
    if (id == 'cto') return 'CTO';
    if (id == 'user') return 'You';
    return id
        .split('_')
        .where((part) => part.isNotEmpty)
        .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
  }
}
