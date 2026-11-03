import 'package:arc/frontend/user_messages.dart';
import 'dart:async';
import 'dart:convert';

import 'package:arc/frontend/company_api_client.dart';
import 'package:flutter/material.dart';

class CompanyCeoWorkspace extends StatefulWidget {
  const CompanyCeoWorkspace({
    super.key,
    required this.api,
    required this.sessionId,
    this.initialCatalog,
    this.enableLiveUpdates = true,
  });

  final CompanyApiClient api;
  final String sessionId;
  final CompanyCatalog? initialCatalog;
  final bool enableLiveUpdates;

  @override
  State<CompanyCeoWorkspace> createState() => _CompanyCeoWorkspaceState();
}

class _CompanyCeoWorkspaceState extends State<CompanyCeoWorkspace> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _chatScroll = ScrollController();
  final Map<int, CompanyEvent> _eventsById = {};
  StreamSubscription<CompanyEvent>? _eventSubscription;
  Timer? _streamRetry;
  Timer? _groupsRefresh;
  CompanyCatalog? _catalog;
  List<CompanyGroup> _groups = const [];
  List<CompanyApproval> _approvals = const [];
  bool _loading = true;
  bool _sending = false;
  bool _live = false;
  String? _pendingPrompt;
  String? _error;

  List<CompanyEvent> get _events {
    final result = _eventsById.values.toList();
    result.sort((a, b) => a.id.compareTo(b.id));
    return result;
  }

  int get _lastEventId => _eventsById.keys.fold(0, (a, b) => a > b ? a : b);

  @override
  void initState() {
    super.initState();
    _catalog = widget.initialCatalog;
    _loadSession();
  }

  Future<void> _loadSession() async {
    try {
      final futures = <Future<Object>>[
        if (_catalog == null) widget.api.loadCatalog(),
        widget.api.loadGroups(widget.sessionId),
        widget.api.loadEvents(widget.sessionId),
      ];
      final results = await Future.wait<Object>(futures);
      var index = 0;
      final catalog = _catalog ?? results[index++] as CompanyCatalog;
      final groups = results[index++] as List<CompanyGroup>;
      final eventPage = results[index] as CompanyEventsPage;
      if (!mounted) return;
      setState(() {
        _catalog = catalog;
        _groups = groups;
        _mergeEvents(eventPage.events);
        _loading = false;
        _error = null;
      });
      if (widget.enableLiveUpdates) _startEventStream();
      _scrollToBottom();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = requestFailureMessage();
      });
    }
  }

  void _startEventStream() {
    _eventSubscription?.cancel();
    _streamRetry?.cancel();
    setState(() => _live = true);
    _eventSubscription = widget.api
        .watchEvents(widget.sessionId, afterId: _lastEventId)
        .listen(
          _receiveEvent,
          onError: (Object error) {
            if (!mounted) return;
            setState(() => _live = false);
            _streamRetry = Timer(const Duration(seconds: 2), () {
              if (mounted) _startEventStream();
            });
          },
          onDone: () {
            if (mounted) setState(() => _live = false);
          },
        );
  }

  void _receiveEvent(CompanyEvent event) {
    if (!mounted) return;
    setState(() {
      _eventsById[event.id] = event;
      if (event.type == 'user_message' && event.content == _pendingPrompt) {
        _pendingPrompt = null;
      }
      _live = true;
    });
    if (event.type == 'group_created' || event.type == 'member_added') {
      _groupsRefresh?.cancel();
      _groupsRefresh = Timer(const Duration(milliseconds: 200), _refreshGroups);
    }
    _scrollToBottom();
  }

  void _mergeEvents(Iterable<CompanyEvent> events) {
    for (final event in events) {
      _eventsById[event.id] = event;
      if (event.type == 'user_message' && event.content == _pendingPrompt) {
        _pendingPrompt = null;
      }
    }
  }

  Future<void> _refreshGroups() async {
    try {
      final groups = await widget.api.loadGroups(widget.sessionId);
      if (mounted) setState(() => _groups = groups);
    } catch (_) {
      // The next CEO response or manual refresh will reconcile group state.
    }
  }

  Future<void> _refreshAll() async {
    try {
      final results = await Future.wait<Object>([
        widget.api.loadGroups(widget.sessionId),
        widget.api.loadEvents(widget.sessionId, afterId: _lastEventId),
      ]);
      if (!mounted) return;
      setState(() {
        _groups = results[0] as List<CompanyGroup>;
        _mergeEvents((results[1] as CompanyEventsPage).events);
        _error = null;
      });
      _scrollToBottom();
    } catch (error) {
      if (mounted) setState(() => _error = requestFailureMessage());
    }
  }

  Future<void> _sendMessage() async {
    final prompt = _controller.text.trim();
    if (prompt.isEmpty || _sending) return;
    _controller.clear();
    setState(() {
      _sending = true;
      _pendingPrompt = prompt;
      _error = null;
    });
    _scrollToBottom();
    try {
      final result = await widget.api.runCeo(
        prompt: prompt,
        sessionId: widget.sessionId,
      );
      if (!mounted) return;
      setState(() {
        _groups = result.groups;
        _mergeEvents(result.events);
        _approvals = result.approvals;
        _pendingPrompt = null;
        _sending = false;
      });
      _scrollToBottom();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _sending = false;
        _pendingPrompt = null;
        _error = requestFailureMessage();
        _controller.text = prompt;
        _controller.selection = TextSelection.collapsed(
          offset: _controller.text.length,
        );
      });
    }
  }

  Future<void> _decideApproval(CompanyApproval approval, bool approve) async {
    try {
      await widget.api.decideApproval(
        approval: approval,
        sessionId: widget.sessionId,
        approve: approve,
      );
      if (!mounted) return;
      setState(() {
        _approvals = _approvals
            .where((item) => item.id != approval.id)
            .toList();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(approve ? 'Action approved.' : 'Action denied.'),
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Your decision could not be saved. Please try again.',
            ),
          ),
        );
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_chatScroll.hasClients) return;
      _chatScroll.animateTo(
        _chatScroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    });
  }

  String _agentName(String id) => _catalog?.agent(id)?.name ?? id;

  @override
  void dispose() {
    _eventSubscription?.cancel();
    _streamRetry?.cancel();
    _groupsRefresh?.cancel();
    _controller.dispose();
    _chatScroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF090909),
      appBar: AppBar(
        backgroundColor: const Color(0xFF090909),
        foregroundColor: Colors.white,
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Company CEO'),
            Text(
              'You can message the CEO only',
              style: TextStyle(fontSize: 11, color: Color(0xFF9B9B9B)),
            ),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: Chip(
              visualDensity: VisualDensity.compact,
              avatar: Icon(
                Icons.circle,
                size: 10,
                color: _live
                    ? const Color(0xFF35C58A)
                    : const Color(0xFF777777),
              ),
              label: Text(_live ? 'Live' : 'Sync'),
            ),
          ),
          IconButton(
            tooltip: 'Refresh',
            onPressed: _refreshAll,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth >= 850) {
              return Row(
                children: [
                  Expanded(flex: 5, child: _buildConversation()),
                  const VerticalDivider(width: 1, color: Color(0xFF303030)),
                  Expanded(flex: 4, child: _buildGroups()),
                ],
              );
            }
            return DefaultTabController(
              length: 2,
              child: Column(
                children: [
                  const TabBar(
                    tabs: [
                      Tab(text: 'CEO chat'),
                      Tab(text: 'Groups'),
                    ],
                  ),
                  Expanded(
                    child: TabBarView(
                      children: [_buildConversation(), _buildGroups()],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildConversation() {
    final conversation = _events
        .where(
          (event) =>
              event.groupId == null &&
              (event.type == 'user_message' || event.type == 'ceo_response'),
        )
        .toList();
    return Column(
      children: [
        if (_error != null)
          MaterialBanner(
            content: Text(_error!),
            actions: [
              TextButton(onPressed: _refreshAll, child: const Text('Retry')),
            ],
          ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  controller: _chatScroll,
                  padding: const EdgeInsets.fromLTRB(16, 18, 16, 12),
                  children: [
                    if (conversation.isEmpty && _pendingPrompt == null)
                      const _WelcomeCard(),
                    ...conversation.map(
                      (event) => _MessageBubble(
                        sender: event.senderId == 'user'
                            ? 'You'
                            : _agentName(event.senderId),
                        message: event.content,
                        isUser: event.senderId == 'user',
                        time: event.createdAt,
                      ),
                    ),
                    if (_pendingPrompt != null)
                      _MessageBubble(
                        sender: 'You',
                        message: _pendingPrompt!,
                        isUser: true,
                        pending: true,
                      ),
                    if (_sending)
                      const Align(
                        alignment: Alignment.centerLeft,
                        child: Padding(
                          padding: EdgeInsets.symmetric(vertical: 10),
                          child: _ThinkingIndicator(),
                        ),
                      ),
                    ..._approvals.map(
                      (approval) => _ApprovalCard(
                        approval: approval,
                        onDecision: (value) => _decideApproval(approval, value),
                      ),
                    ),
                  ],
                ),
        ),
        _Composer(
          controller: _controller,
          sending: _sending,
          onSend: _sendMessage,
        ),
      ],
    );
  }

  Widget _buildGroups() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_groups.isEmpty) {
      return const _NoGroupsYet();
    }
    return RefreshIndicator(
      onRefresh: _refreshGroups,
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(14),
        itemCount: _groups.length,
        itemBuilder: (context, index) {
          final group = _groups[index];
          final events = _events
              .where((event) => event.groupId == group.id)
              .toList();
          return _GroupTimelineCard(
            group: group,
            events: events,
            agentName: _agentName,
          );
        },
      ),
    );
  }
}

class _WelcomeCard extends StatelessWidget {
  const _WelcomeCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 30),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF181818),
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Column(
        children: [
          CircleAvatar(
            radius: 28,
            backgroundColor: Color(0xFF2B6EF3),
            child: Icon(Icons.business_center, color: Colors.white),
          ),
          SizedBox(height: 14),
          Text(
            'Talk to your CEO',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Describe the company or project you want. The CEO decides when to create a group and which director should lead it.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFFAAAAAA), height: 1.45),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.sender,
    required this.message,
    required this.isUser,
    this.time,
    this.pending = false,
  });

  final String sender;
  final String message;
  final bool isUser;
  final DateTime? time;
  final bool pending;

  @override
  Widget build(BuildContext context) {
    final hour = time?.hour.toString().padLeft(2, '0');
    final minute = time?.minute.toString().padLeft(2, '0');
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 620),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
        decoration: BoxDecoration(
          color: isUser ? const Color(0xFF2B6EF3) : const Color(0xFF202020),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              sender,
              style: TextStyle(
                color: isUser ? Colors.white70 : const Color(0xFF73A0FF),
                fontSize: 11,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            SelectableText(
              message,
              style: const TextStyle(color: Colors.white, height: 1.4),
            ),
            if (pending || time != null) ...[
              const SizedBox(height: 5),
              Text(
                pending ? 'Sending…' : '$hour:$minute',
                style: const TextStyle(color: Colors.white54, fontSize: 10),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ThinkingIndicator extends StatelessWidget {
  const _ThinkingIndicator();

  @override
  Widget build(BuildContext context) {
    return const Chip(
      avatar: SizedBox(
        width: 14,
        height: 14,
        child: CircularProgressIndicator(strokeWidth: 2),
      ),
      label: Text('CEO and team are working…'),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.sending,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        12,
        8,
        12,
        12 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: TextField(
        controller: controller,
        enabled: !sending,
        minLines: 1,
        maxLines: 5,
        textInputAction: TextInputAction.newline,
        style: const TextStyle(color: Colors.white),
        decoration: InputDecoration(
          hintText: 'Message the CEO',
          hintStyle: const TextStyle(color: Color(0xFF8E8E8E)),
          filled: true,
          fillColor: const Color(0xFF222222),
          contentPadding: const EdgeInsets.fromLTRB(18, 14, 8, 14),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(26),
            borderSide: const BorderSide(color: Color(0xFF3A3A3A)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(26),
            borderSide: const BorderSide(color: Color(0xFF3A3A3A)),
          ),
          suffixIcon: IconButton.filled(
            tooltip: 'Send to CEO',
            onPressed: sending ? null : onSend,
            icon: sending
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.arrow_upward),
          ),
        ),
      ),
    );
  }
}

class _NoGroupsYet extends StatelessWidget {
  const _NoGroupsYet();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.groups_outlined, color: Color(0xFF777777), size: 48),
            SizedBox(height: 12),
            Text(
              'No company groups yet',
              style: TextStyle(color: Colors.white),
            ),
            SizedBox(height: 6),
            Text(
              'A group will appear when the CEO delegates work to a director.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Color(0xFF999999)),
            ),
          ],
        ),
      ),
    );
  }
}

class _GroupTimelineCard extends StatelessWidget {
  const _GroupTimelineCard({
    required this.group,
    required this.events,
    required this.agentName,
  });

  final CompanyGroup group;
  final List<CompanyEvent> events;
  final String Function(String id) agentName;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF191919),
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        initiallyExpanded: true,
        iconColor: Colors.white,
        collapsedIconColor: Colors.white70,
        leading: const CircleAvatar(
          backgroundColor: Color(0xFF273D69),
          child: Icon(Icons.groups_2_outlined, color: Colors.white),
        ),
        title: Text(
          group.name,
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w700,
          ),
        ),
        subtitle: Text(
          group.objective,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Color(0xFFA0A0A0)),
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Wrap(
              spacing: 6,
              runSpacing: 6,
              children: group.members
                  .map(
                    (member) => Chip(
                      visualDensity: VisualDensity.compact,
                      label: Text(agentName(member.agentId)),
                      avatar: Icon(
                        member.role == 'director'
                            ? Icons.supervisor_account
                            : Icons.person,
                        size: 16,
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
          const Divider(height: 24, color: Color(0xFF333333)),
          if (events.isEmpty)
            const Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Waiting for team activity…',
                style: TextStyle(color: Color(0xFF888888)),
              ),
            )
          else
            ...events.map(
              (event) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _EventIcon(type: event.type),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${agentName(event.senderId)} → ${agentName(event.recipientId)}',
                            style: const TextStyle(
                              color: Color(0xFF73A0FF),
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            event.content,
                            style: const TextStyle(
                              color: Color(0xFFE5E5E5),
                              height: 1.35,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _EventIcon extends StatelessWidget {
  const _EventIcon({required this.type});

  final String type;

  @override
  Widget build(BuildContext context) {
    final icon = switch (type) {
      'group_created' => Icons.group_add_outlined,
      'member_added' => Icons.person_add_alt,
      'task_delegated' => Icons.assignment_outlined,
      'agent_report' => Icons.summarize_outlined,
      _ => Icons.circle_outlined,
    };
    return Icon(icon, size: 18, color: const Color(0xFF9A9A9A));
  }
}

class _ApprovalCard extends StatelessWidget {
  const _ApprovalCard({required this.approval, required this.onDecision});

  final CompanyApproval approval;
  final ValueChanged<bool> onDecision;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF352C16),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${approval.role} requests ${approval.tool}',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            SelectableText(
              const JsonEncoder.withIndent('  ').convert(approval.arguments),
              style: const TextStyle(color: Color(0xFFD0D0D0), fontSize: 12),
            ),
            const SizedBox(height: 10),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: () => onDecision(false),
                  child: const Text('Deny'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: () => onDecision(true),
                  child: const Text('Approve once'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
