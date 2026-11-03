import 'package:arc/frontend/arc_design.dart';
import 'package:arc/frontend/chatmessage.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:url_launcher/url_launcher.dart';

Uri? replyLink(String? value) {
  final uri = Uri.tryParse(value ?? '');
  return uri != null &&
          uri.scheme == 'https' &&
          uri.host.isNotEmpty &&
          uri.userInfo.isEmpty
      ? uri
      : null;
}

class ChatReply extends StatelessWidget {
  const ChatReply({super.key, required this.text});
  final String text;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final compact = constraints.maxWidth < 600;
      final body = TextStyle(
        fontSize: compact ? 15 : 16,
        height: 1.65,
        color: const Color(0xFFE7ECE6),
      );
      final heading = body.copyWith(
        color: const Color(0xFFF5F7F2),
        fontWeight: FontWeight.w700,
        height: 1.3,
      );
      return SelectionArea(
        child: MarkdownBody(
          data: text,
          fitContent: false,
          styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
            p: body,
            pPadding: EdgeInsets.zero,
            strong: body.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w700,
            ),
            em: body.copyWith(fontStyle: FontStyle.italic),
            h1: heading.copyWith(fontSize: compact ? 24 : 28),
            h2: heading.copyWith(fontSize: compact ? 21 : 23),
            h3: heading.copyWith(fontSize: 18),
            h4: heading.copyWith(fontSize: 16),
            h1Padding: const EdgeInsets.only(top: 4, bottom: 4),
            h2Padding: const EdgeInsets.only(top: 4, bottom: 2),
            h3Padding: const EdgeInsets.only(top: 4),
            blockSpacing: 16,
            listIndent: 24,
            listBullet: body.copyWith(
              color: arcLime,
              fontWeight: FontWeight.w600,
            ),
            listBulletPadding: const EdgeInsets.only(right: 10, top: 1),
            a: body.copyWith(
              color: arcLime,
              decoration: TextDecoration.underline,
            ),
            code: const TextStyle(
              fontFamily: 'monospace',
              fontSize: 13,
              height: 1.6,
              color: arcLime,
              backgroundColor: Color(0xFF1E2820),
            ),
            codeblockPadding: const EdgeInsets.all(16),
            codeblockDecoration: BoxDecoration(
              color: const Color(0xFF151D17),
              border: Border.all(color: const Color(0xFF2D3A30)),
              borderRadius: BorderRadius.circular(14),
            ),
            blockquote: body.copyWith(color: const Color(0xFFBDCFB7)),
            blockquotePadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 12,
            ),
            blockquoteDecoration: const BoxDecoration(
              color: Color(0xFF152017),
              border: Border(left: BorderSide(color: arcLime, width: 3)),
            ),
            tableHead: body.copyWith(
              color: arcLime,
              fontWeight: FontWeight.w700,
            ),
            tableBody: body.copyWith(fontSize: compact ? 14 : 15),
            tableHeadAlign: TextAlign.left,
            tableColumnWidth: FixedColumnWidth(
              compact ? 170 : (constraints.maxWidth - 2) / 2,
            ),
            tableCellsPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 13,
            ),
            tableHeadCellsPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 14,
            ),
            tableCellsDecoration: const BoxDecoration(color: Color(0xFF121A14)),
            tableHeadCellsDecoration: const BoxDecoration(
              color: Color(0xFF202E22),
            ),
            tableBorder: TableBorder.all(color: const Color(0xFF354336)),
            horizontalRuleDecoration: const BoxDecoration(
              border: Border(top: BorderSide(color: Color(0xFF2B352D))),
            ),
          ),
          onTapLink: (_, href, _) {
            final uri = replyLink(href);
            if (uri != null) {
              launchUrl(uri, mode: LaunchMode.externalApplication);
            }
          },
          // Model-supplied images must not make automatic network or file reads.
          imageBuilder: (_, title, alt) => Text(
            alt?.isNotEmpty == true
                ? alt!
                : (title?.isNotEmpty == true ? title! : 'Image'),
            style: body.copyWith(color: arcLilac, fontStyle: FontStyle.italic),
          ),
        ),
      );
    },
  );
}

class ChatMessageView extends StatelessWidget {
  const ChatMessageView({super.key, required this.message});
  final Chatmessage message;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      if (message.isMe) {
        return Align(
          alignment: Alignment.centerRight,
          child: Container(
            constraints: BoxConstraints(maxWidth: constraints.maxWidth * .82),
            margin: const EdgeInsets.fromLTRB(16, 12, 16, 18),
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
            decoration: BoxDecoration(
              color: const Color(0xFF2B332E),
              border: Border.all(color: const Color(0xFF3A453E)),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(23),
                topRight: Radius.circular(8),
                bottomLeft: Radius.circular(23),
                bottomRight: Radius.circular(23),
              ),
            ),
            child: Text(
              message.text,
              style: const TextStyle(
                fontSize: 15,
                height: 1.5,
                color: Colors.white,
              ),
            ),
          ),
        );
      }
      return Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        child: ChatReply(text: message.text),
      );
    },
  );
}
