class Chatmessage {
  final String text;

  final bool isMe;
  final bool isAI;
  final bool istyping;

  Chatmessage({
    required this.text,
    this.isAI = false,
    this.isMe = false,
    this.istyping = false,
  });
}
