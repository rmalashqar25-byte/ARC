import 'dart:math' as math;
import 'package:flutter/material.dart';

const arcLime = Color(0xFFD7F6A2);
const arcLilac = Color(0xFFC9B9FF);
const arcCanvas = Color(0xFF0B0D0C);
const arcPanel = Color(0xFF151916);

class ArcOrbit extends StatelessWidget {
  const ArcOrbit({super.key, this.size = 180});
  final double size;
  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: SizedBox.square(
      dimension: size,
      child: CustomPaint(painter: _OrbitPainter()),
    ),
  );
}

class _OrbitPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.width * .39;
    final line = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    for (var i = 0; i < 3; i++) {
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(i * math.pi / 3);
      line.color = [arcLime, arcLilac, Colors.white][i].withValues(alpha: .3);
      canvas.drawOval(
        Rect.fromCenter(
          center: Offset.zero,
          width: radius * 2,
          height: radius * .8,
        ),
        line,
      );
      canvas.restore();
    }
    final glow = Paint()
      ..shader = const RadialGradient(
        colors: [Color(0x554F7030), Color(0x004F7030)],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius, glow);
    canvas.drawCircle(center, size.width * .10, Paint()..color = arcLime);
    canvas.drawCircle(
      center + Offset(radius * .86, -radius * .18),
      5,
      Paint()..color = arcLilac,
    );
    canvas.drawCircle(
      center + Offset(-radius * .45, radius * .59),
      4,
      Paint()..color = Colors.white,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class ArcNotice extends StatelessWidget {
  const ArcNotice({super.key, required this.message, this.onRetry});
  final String message;
  final VoidCallback? onRetry;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: const Color(0xFF23251C),
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: const Color(0xFF41452D)),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.wifi_off_rounded, size: 20, color: arcLime),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            message,
            style: const TextStyle(color: Color(0xFFE2E3CE), height: 1.5),
          ),
        ),
        if (onRetry != null)
          IconButton(
            tooltip: 'Retry connection',
            onPressed: onRetry,
            icon: const Icon(Icons.refresh, color: arcLime),
          ),
      ],
    ),
  );
}

class ArcPathCard extends StatefulWidget {
  const ArcPathCard({
    super.key,
    required this.eyebrow,
    required this.title,
    required this.description,
    required this.icon,
    required this.color,
    required this.onTap,
  });
  final String eyebrow, title, description;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  @override
  State<ArcPathCard> createState() => _ArcPathCardState();
}

class _ArcPathCardState extends State<ArcPathCard> {
  bool _hover = false;
  @override
  Widget build(BuildContext context) => MouseRegion(
    onEnter: (_) => setState(() => _hover = true),
    onExit: (_) => setState(() => _hover = false),
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      decoration: BoxDecoration(
        color: _hover ? const Color(0xFF222A21) : arcPanel,
        borderRadius: BorderRadius.circular(26),
        border: Border.all(
          color: _hover ? widget.color : const Color(0xFF30382F),
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: widget.onTap,
          borderRadius: BorderRadius.circular(26),
          child: Padding(
            padding: const EdgeInsets.all(26),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(13),
                      decoration: BoxDecoration(
                        color: widget.color.withValues(alpha: .12),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Icon(widget.icon, color: widget.color, size: 28),
                    ),
                    const Spacer(),
                    Icon(Icons.north_east, color: widget.color),
                  ],
                ),
                const SizedBox(height: 32),
                Text(
                  widget.eyebrow,
                  style: TextStyle(
                    color: widget.color,
                    fontSize: 11,
                    letterSpacing: 2,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  widget.title,
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  widget.description,
                  style: const TextStyle(color: Colors.white60, height: 1.6),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
