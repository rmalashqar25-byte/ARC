import 'package:flutter/material.dart';
import 'arc_design.dart';
import 'chatsession.dart';

class ArcSidebar extends StatefulWidget {
  const ArcSidebar({
    super.key,
    required this.sessions,
    required this.activeSessionId,
    required this.onNewChat,
    required this.onCompany,
    required this.onMarketplace,
    required this.onPlugins,
    required this.onSettings,
    required this.onClose,
    required this.onOpenSession,
    required this.onSessionActions,
  });
  final List<ChatSession> sessions;
  final String activeSessionId;
  final VoidCallback onNewChat,
      onCompany,
      onMarketplace,
      onPlugins,
      onSettings,
      onClose;
  final ValueChanged<ChatSession> onOpenSession, onSessionActions;
  @override
  State<ArcSidebar> createState() => _ArcSidebarState();
}

class _ArcSidebarState extends State<ArcSidebar> {
  final _search = TextEditingController();
  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Widget _navigation(String label, IconData icon, VoidCallback onTap) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 5),
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(14),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
              child: Row(
                children: [
                  Icon(icon, color: const Color(0xFFBCC6BA), size: 21),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: Color(0xFFE8EDE6),
                      ),
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right,
                    size: 17,
                    color: Color(0xFF656F64),
                  ),
                ],
              ),
            ),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final query = _search.text.trim().toLowerCase();
    final sessions = widget.sessions.reversed
        .where((s) => s.title.toLowerCase().contains(query))
        .toList();
    return Drawer(
      width: (MediaQuery.sizeOf(context).width - 28).clamp(0, 344).toDouble(),
      backgroundColor: arcCanvas,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.horizontal(right: Radius.circular(24)),
        side: BorderSide(color: Color(0xFF283026)),
      ),
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 14, 10, 14),
              child: Row(
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: arcLime.withValues(alpha: .08),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: arcLime.withValues(alpha: .15)),
                    ),
                    child: const ArcOrbit(size: 42),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'ARC',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w600,
                            letterSpacing: -.5,
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Your founder workspace',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 11,
                            color: Color(0xFF8C988A),
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close sidebar',
                    onPressed: widget.onClose,
                    icon: const Icon(
                      Icons.close_rounded,
                      color: Color(0xFF8C988A),
                      size: 20,
                    ),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: Color(0xFF252D23)),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(14, 18, 14, 18),
                children: [
                  FilledButton.icon(
                    onPressed: widget.onNewChat,
                    style: FilledButton.styleFrom(
                      backgroundColor: arcLime,
                      foregroundColor: const Color(0xFF14200A),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 17,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(15),
                      ),
                    ),
                    icon: const Icon(Icons.add_rounded, size: 21),
                    label: const Text(
                      'New conversation',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  const Padding(
                    padding: EdgeInsets.only(left: 12, bottom: 10),
                    child: Text(
                      'WORKSPACE',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.7,
                        color: Color(0xFF788674),
                      ),
                    ),
                  ),
                  _navigation(
                    'Company workspace',
                    Icons.business_outlined,
                    widget.onCompany,
                  ),
                  _navigation(
                    'The collective',
                    Icons.storefront_outlined,
                    widget.onMarketplace,
                  ),
                  _navigation(
                    'Plugins',
                    Icons.extension_outlined,
                    widget.onPlugins,
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 10, vertical: 17),
                    child: Divider(height: 1, color: Color(0xFF283026)),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Row(
                      children: [
                        const Expanded(
                          child: Text(
                            'RECENT CHATS',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 1.7,
                              color: Color(0xFF788674),
                            ),
                          ),
                        ),
                        if (widget.sessions.isNotEmpty)
                          Text(
                            '${widget.sessions.length}',
                            style: const TextStyle(
                              fontSize: 11,
                              color: Color(0xFF788674),
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  if (widget.sessions.isNotEmpty) ...[
                    TextField(
                      controller: _search,
                      onChanged: (_) => setState(() {}),
                      style: const TextStyle(fontSize: 13),
                      decoration: InputDecoration(
                        hintText: 'Search conversations',
                        isDense: true,
                        hintStyle: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFF6E7B6B),
                        ),
                        prefixIcon: const Icon(
                          Icons.search,
                          size: 18,
                          color: Color(0xFF8D9989),
                        ),
                        suffixIcon: query.isEmpty
                            ? null
                            : IconButton(
                                tooltip: 'Clear conversation search',
                                icon: const Icon(Icons.close, size: 16),
                                onPressed: () =>
                                    setState(() => _search.clear()),
                              ),
                        filled: true,
                        fillColor: arcPanel,
                        contentPadding: const EdgeInsets.symmetric(
                          vertical: 13,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(13),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                  ],
                  if (widget.sessions.isEmpty)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 18,
                        vertical: 22,
                      ),
                      decoration: BoxDecoration(
                        color: arcPanel,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: const Color(0xFF252F22)),
                      ),
                      child: const Column(
                        children: [
                          Icon(
                            Icons.chat_bubble_outline_rounded,
                            color: Color(0xFF7D9373),
                            size: 25,
                          ),
                          SizedBox(height: 14),
                          Text(
                            'Your next idea starts here.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                              color: Color(0xFFD8E1D2),
                            ),
                          ),
                          SizedBox(height: 8),
                          Text(
                            'Start a conversation with your CEO.\nYou’ll find it here as you build.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 12,
                              height: 1.6,
                              color: Color(0xFF83917D),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (widget.sessions.isNotEmpty && sessions.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(20),
                      child: Text(
                        'No matching conversations',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Color(0xFF8C988A),
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ...sessions.map((session) {
                    final active = session.id == widget.activeSessionId;
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 5),
                      child: Material(
                        color: active
                            ? const Color(0xFF202D1B)
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(13),
                        child: InkWell(
                          onTap: () => widget.onOpenSession(session),
                          onLongPress: () => widget.onSessionActions(session),
                          borderRadius: BorderRadius.circular(13),
                          child: Padding(
                            padding: const EdgeInsets.only(left: 12),
                            child: Row(
                              children: [
                                Icon(
                                  Icons.chat_bubble_outline_rounded,
                                  size: 16,
                                  color: active
                                      ? arcLime
                                      : const Color(0xFF7F8A7B),
                                ),
                                const SizedBox(width: 11),
                                Expanded(
                                  child: Text(
                                    session.title,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 13,
                                      color: active
                                          ? const Color(0xFFE2F0D6)
                                          : const Color(0xFFB5C0AF),
                                    ),
                                  ),
                                ),
                                IconButton(
                                  tooltip: 'Chat options for ${session.title}',
                                  onPressed: () =>
                                      widget.onSessionActions(session),
                                  icon: const Icon(
                                    Icons.more_horiz,
                                    size: 19,
                                    color: Color(0xFF889581),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    );
                  }),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 16),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: Color(0xFF252D23))),
              ),
              child: Material(
                color: arcPanel,
                borderRadius: BorderRadius.circular(16),
                child: InkWell(
                  onTap: widget.onSettings,
                  borderRadius: BorderRadius.circular(16),
                  child: Padding(
                    padding: const EdgeInsets.all(13),
                    child: Row(
                      children: [
                        const CircleAvatar(
                          radius: 19,
                          backgroundColor: Color(0xFF302A3F),
                          child: Icon(
                            Icons.tune_rounded,
                            color: arcLilac,
                            size: 20,
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Workspace settings',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              SizedBox(height: 4),
                              Text(
                                'Preferences & agent access',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Color(0xFF8C988A),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const Icon(
                          Icons.chevron_right,
                          color: Color(0xFF889581),
                          size: 18,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
