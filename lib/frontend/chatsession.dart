import 'package:arc/frontend/chatmessage.dart';

class ChatSession {
  final String title;
  final String id;
  final List<Chatmessage> messages;

  ChatSession({
    required this.title,
    required this.id,
    List<Chatmessage>? messages,
  }) : messages = messages ?? [];
}
