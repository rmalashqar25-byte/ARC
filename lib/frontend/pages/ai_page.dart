import 'package:arc/frontend/pages/companypage/work_board.dart';
import 'package:arc/api_config.dart';
import 'package:arc/frontend/arc_design.dart';
import 'package:arc/frontend/arc_sidebar.dart';
import 'package:arc/frontend/chatmessage.dart';
import 'package:arc/frontend/chat_reply.dart';
import 'package:arc/frontend/chatsession.dart';
import 'package:arc/frontend/company_api_client.dart';
import 'package:arc/frontend/company_live_activity.dart';
import 'package:arc/frontend/pages/workspace_settings.dart';

import 'package:arc/frontend/pages/companypage/company.dart' as componypage;
import 'package:arc/frontend/pages/plugins.dart';
import 'package:arc/frontend/pages/companypage/market.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'package:uuid/uuid.dart';

enum _SessionAction { rename, delete }

class AiPage extends StatefulWidget {
  const AiPage({super.key});

  @override
  State<AiPage> createState() => _AipageState();
}

class _AipageState extends State<AiPage> {
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final TextEditingController controller = TextEditingController();
  final uuid = const Uuid();
  List<Chatmessage> chat = [];
  final List<ChatSession> chatSession = [];
  bool _isSending = false;
  String? _pausedWorkSession;
  bool _showActivity = false;

  String id = "";
  final CompanyApiClient _activityApi = CompanyApiClient();

  @override
  void initState() {
    super.initState();
    _connectLocalTerminal();
  }

  Future<void> _connectLocalTerminal() async {
    try {
      await http
          .post(
            ApiConfig.endpoint('/plugins/terminal/auto-connect'),
            headers: {
              ...ApiConfig.headers(),
              'Content-Type': 'application/json',
            },
            body: '{}',
          )
          .timeout(const Duration(seconds: 15));
    } catch (_) {
      // Optional local service; opening the chat never waits for it.
    }
  }

  @override
  void dispose() {
    controller.dispose();
    _activityApi.close();
    super.dispose();
  }

  void openNewChat() {
    setState(() {
      id = "";
      ApiConfig.companySessionId = uuid.v4();
      chat = [];
    });
  }

  void openSession(ChatSession session) {
    setState(() {
      id = session.id;
      ApiConfig.companySessionId = session.id;
      chat = session.messages;
    });
  }

  Map<String, String> _authenticatedHeaders() => ApiConfig.headers();

  Future<void> _showSessionActions(ChatSession session) async {
    final action = await showDialog<_SessionAction>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(
          session.title,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        contentPadding: const EdgeInsets.only(top: 12, bottom: 8),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: const Text('Rename'),
              onTap: () =>
                  Navigator.of(dialogContext).pop(_SessionAction.rename),
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline, color: Colors.red),
              title: const Text('Delete', style: TextStyle(color: Colors.red)),
              onTap: () =>
                  Navigator.of(dialogContext).pop(_SessionAction.delete),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );

    if (!mounted || action == null) return;
    switch (action) {
      case _SessionAction.rename:
        await _renameSession(session);
      case _SessionAction.delete:
        await _deleteSession(session);
    }
  }

  Future<void> _renameSession(ChatSession session) async {
    var editedTitle = session.title;
    var canSave = session.title.trim().isNotEmpty;

    final newTitle = await showDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Rename chat'),
          content: TextFormField(
            initialValue: session.title,
            autofocus: true,
            maxLength: 80,
            textInputAction: TextInputAction.done,
            decoration: const InputDecoration(
              labelText: 'Chat name',
              border: OutlineInputBorder(),
            ),
            onChanged: (value) {
              editedTitle = value;
              final nextCanSave = value.trim().isNotEmpty;
              if (nextCanSave != canSave) {
                setDialogState(() => canSave = nextCanSave);
              }
            },
            onFieldSubmitted: (value) {
              final title = value.trim();
              if (title.isNotEmpty) Navigator.of(dialogContext).pop(title);
            },
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: canSave
                  ? () => Navigator.of(dialogContext).pop(editedTitle.trim())
                  : null,
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );

    if (!mounted || newTitle == null || newTitle == session.title) return;
    final sessionIndex = chatSession.indexWhere(
      (candidate) => candidate.id == session.id,
    );
    if (sessionIndex == -1) return;

    setState(() {
      chatSession[sessionIndex] = ChatSession(
        title: newTitle,
        id: session.id,
        messages: session.messages,
      );
    });
  }

  Future<void> _deleteSession(ChatSession session) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Delete chat?'),
        content: Text(
          '“${session.title}” and its conversation history will be deleted.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true) return;

    try {
      final response = await http
          .delete(
            ApiConfig.endpoint(
              '/company/sessions/${Uri.encodeComponent(session.id)}',
            ),
            headers: _authenticatedHeaders(),
          )
          .timeout(const Duration(seconds: 15));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw http.ClientException(
          'Server returned ${response.statusCode}',
          response.request?.url,
        );
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not delete this chat. Please try again.'),
        ),
      );
      return;
    }

    if (!mounted) return;
    setState(() {
      chatSession.removeWhere((candidate) => candidate.id == session.id);
      if (id == session.id) {
        id = '';
        chat = [];
        controller.clear();
      }
    });
  }

  Future<CompanyCeoResult> askCeo(String prompt, String sessionId) async {
    final api = CompanyApiClient();
    try {
      return await api.runCeo(prompt: prompt, sessionId: sessionId);
    } finally {
      api.close();
    }
  }

  Future<void> _sendMessage() async {
    final prompt = controller.text.trim();
    if (prompt.isEmpty || _isSending) return;

    if (id.isEmpty) {
      id = ApiConfig.companySessionId;
      ApiConfig.companySessionId = id;
      chatSession.add(ChatSession(title: prompt, id: id, messages: chat));
    }

    final activeChat = chat;
    final activeSessionId = id;
    setState(() {
      activeChat.add(Chatmessage(text: prompt, isMe: true));
      _isSending = true;
    });
    controller.clear();

    String answer;
    try {
      final reply = await askCeo(prompt, activeSessionId);
      answer = reply.message;
      _pausedWorkSession = answer.contains('Automatic work is paused')
          ? activeSessionId
          : null;
    } catch (error) {
      answer = error is CompanyApiException
          ? error.message
          : 'ARC is temporarily unavailable. Please try again in a moment.';
    }

    if (!mounted) return;
    setState(() {
      activeChat.add(Chatmessage(text: answer, isAI: true));
      _isSending = false;
    });
  }

  Future<void> _openMarketplace() async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) =>
            Market(sessionId: id.isEmpty ? ApiConfig.companySessionId : id),
      ),
    );
    if (mounted) setState(() {});
  }

  Future<void> _letCeoChoose() async {
    try {
      final session = id.isEmpty ? ApiConfig.companySessionId : id;
      final current = await _activityApi.loadProjectTeam(session);
      await _activityApi.saveProjectTeam(
        session,
        'ceo',
        (current['members'] as List)
            .map((m) => Map<String, String>.from(m as Map))
            .toList(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'The CEO will choose your team. Describe your company to begin.',
          ),
        ),
      );
      controller.text = 'Help me build a company. Choose the team for me. ';
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Your team preference could not be saved. Please try again.',
            ),
          ),
        );
      }
    }
  }

  Widget _welcome() => SingleChildScrollView(
    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const ArcOrbit(size: 140),
        const Text(
          'YOUR IDEA. OUR NEXT CHAPTER.',
          style: TextStyle(
            color: arcLime,
            fontSize: 10,
            letterSpacing: 2.4,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 18),
        const Text(
          'An idea today.\nA company tomorrow.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 38,
            height: 1.12,
            letterSpacing: -1.2,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 18),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 490),
          child: const Text(
            'I’m your CEO. Tell me what you want to create. We’ll shape the plan, find the right minds, and build it together.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white60, height: 1.7, fontSize: 15),
          ),
        ),
        const SizedBox(height: 25),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          alignment: WrapAlignment.center,
          children: [
            OutlinedButton.icon(
              onPressed: _openMarketplace,
              icon: const Icon(Icons.people_outline, size: 18),
              label: const Text('Choose my agents'),
            ),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: arcLime,
                foregroundColor: Colors.black,
              ),
              onPressed: _letCeoChoose,
              icon: const Icon(Icons.auto_awesome, size: 18),
              label: const Text('Let the CEO choose'),
            ),
          ],
        ),
        const SizedBox(height: 22),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 8,
          runSpacing: 8,
          children: [
            ActionChip(
              label: const Text(
                'Turn my idea into a plan',
                style: TextStyle(fontSize: 11),
              ),
              onPressed: () => controller.text =
                  'Help me turn my idea into a company. Ask me about the idea first.',
            ),
            ActionChip(
              label: const Text(
                'Find my first customers',
                style: TextStyle(fontSize: 11),
              ),
              onPressed: () => controller.text =
                  'Help me find the first customers for my business. Ask me what I’m building.',
            ),
          ],
        ),
      ],
    ),
  );

  void _openSidebarPage(Widget page) {
    _scaffoldKey.currentState?.closeDrawer();
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Scaffold(
        key: _scaffoldKey,

        appBar: AppBar(
          elevation: 0,
          scrolledUnderElevation: 0,
          surfaceTintColor: Colors.transparent,
          foregroundColor: Colors.white,
          automaticallyImplyLeading: false,
          title: Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('ARC', style: TextStyle(fontSize: 22)),
                const SizedBox(width: 10),
                IconButton(
                  tooltip: _showActivity
                      ? 'Hide live stream'
                      : 'Show live stream',
                  icon: const Icon(Icons.open_in_browser_sharp, size: 27),
                  onPressed: () {
                    if (MediaQuery.sizeOf(context).width < 1450) {
                      showModalBottomSheet<void>(
                        context: context,
                        isScrollControlled: true,
                        builder: (sheetContext) => SizedBox(
                          height: MediaQuery.sizeOf(context).height * 0.78,
                          child: CompanyLiveActivity(
                            api: _activityApi,
                            onClose: () => Navigator.of(sheetContext).pop(),
                            sessionId: id.isEmpty
                                ? ApiConfig.companySessionId
                                : id,
                          ),
                        ),
                      );
                    } else {
                      setState(() => _showActivity = !_showActivity);
                    }
                  },
                ),
              ],
            ),
          ),

          actions: [
            Container(
              width: 37,
              height: 40,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: IconButton(
                icon: Icon(Icons.edit_note, color: Colors.white, size: 30),
                onPressed: () {
                  openNewChat();
                },
              ),
            ),
          ],
          leading: UnconstrainedBox(
            child: Container(
              width: 37,
              height: 37,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  borderRadius: BorderRadius.circular(100),
                  onTap: () {
                    _scaffoldKey.currentState?.openDrawer();
                  },

                  child: Center(child: const Icon(Icons.sort, size: 20)),
                ),
              ),
            ),
          ),
          backgroundColor: Colors.transparent,
          iconTheme: const IconThemeData(color: Colors.white),
        ),

        drawer: ArcSidebar(
          sessions: chatSession,
          activeSessionId: id,
          onClose: () => _scaffoldKey.currentState?.closeDrawer(),
          onNewChat: () {
            openNewChat();
            _scaffoldKey.currentState?.closeDrawer();
          },
          onOpenSession: (session) {
            openSession(session);
            _scaffoldKey.currentState?.closeDrawer();
          },
          onSessionActions: _showSessionActions,
          onCompany: () => _openSidebarPage(
            componypage.Company(
              initialSessionId: id.isEmpty ? ApiConfig.companySessionId : id,
            ),
          ),
          onMarketplace: () => _openSidebarPage(
            Market(sessionId: id.isEmpty ? ApiConfig.companySessionId : id),
          ),
          onPlugins: () => _openSidebarPage(const Plugins()),
          onSettings: () => _openSidebarPage(
            WorkspaceSettingsPage(
              sessionId: id.isEmpty ? ApiConfig.companySessionId : id,
            ),
          ),
        ),
        backgroundColor: Colors.black,

        body: Row(
          children: [
            Expanded(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 900),
                  child: Column(
                    children: [
                      if (_pausedWorkSession == id)
                        Padding(
                          padding: const EdgeInsets.all(12),
                          child: FilledButton.icon(
                            icon: const Icon(Icons.play_arrow),
                            label: const Text('Start queued work'),
                            onPressed: () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => WorkBoard(sessionId: id),
                              ),
                            ),
                          ),
                        ),
                      Expanded(
                        child: Center(
                          child: chat.isEmpty
                              ? _welcome()
                              : ListView.builder(
                                  itemCount: chat.length,
                                  itemBuilder: (context, index) {
                                    final message = chat[index];

                                    return ChatMessageView(message: message);
                                  },
                                ),
                        ),
                      ),

                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                        child: TextFormField(
                          controller: controller,
                          minLines: 1,
                          maxLines: 3,
                          textInputAction: TextInputAction.send,
                          onFieldSubmitted: (_) => _sendMessage(),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 15,
                          ),
                          decoration: InputDecoration(
                            hintText: 'Ask ARC',
                            filled: true,
                            fillColor: const Color(0xFF262626),
                            isDense: true,
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 18,
                              vertical: 14,
                            ),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(24),
                              borderSide: BorderSide.none,
                            ),
                            suffixIcon: IconButton(
                              tooltip: 'Send message',
                              onPressed: _isSending ? null : _sendMessage,
                              icon: _isSending
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.send, size: 20),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            if (_showActivity && MediaQuery.sizeOf(context).width >= 1450)
              SizedBox(
                width: 370,
                child: CompanyLiveActivity(
                  api: _activityApi,
                  onClose: () => setState(() => _showActivity = false),
                  sessionId: id.isEmpty ? ApiConfig.companySessionId : id,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
