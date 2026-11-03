import 'package:flutter/material.dart';
import 'arc_design.dart';
import 'market_departments.dart';

class MarketWorkPicker extends StatelessWidget {
  const MarketWorkPicker({
    super.key,
    required this.onDepartment,
    required this.onAllModels,
    required this.onEmployee,
    required this.onOffer,
  });
  final ValueChanged<String> onDepartment;
  final VoidCallback onAllModels, onEmployee, onOffer;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, bounds) {
      final columns = bounds.maxWidth > 960
          ? 3
          : bounds.maxWidth > 620
          ? 2
          : 1;
      final width = (bounds.maxWidth - (columns - 1) * 14) / columns;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'THE ARC COLLECTIVE',
                      style: TextStyle(
                        color: arcLime,
                        fontSize: 11,
                        letterSpacing: 2.5,
                      ),
                    ),
                    const SizedBox(height: 18),
                    Text(
                      'What are we\nworking on?',
                      style: TextStyle(
                        fontSize: bounds.maxWidth > 700 ? 50 : 36,
                        fontWeight: FontWeight.w600,
                        height: 1.08,
                        letterSpacing: -1.5,
                      ),
                    ),
                    const SizedBox(height: 18),
                    const Text(
                      'Choose the work first. Then find the right AI model, discover a specialist, or bring someone from your own team.',
                      style: TextStyle(
                        color: Colors.white60,
                        height: 1.6,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
              ),
              if (bounds.maxWidth > 850) const ArcOrbit(size: 180),
            ],
          ),
          const SizedBox(height: 28),
          Wrap(
            spacing: 14,
            runSpacing: 14,
            children: marketDepartments
                .map(
                  (d) => SizedBox(
                    width: width,
                    child: Material(
                      color: arcPanel,
                      borderRadius: BorderRadius.circular(22),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(22),
                        onTap: () => onDepartment(d.id),
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(d.icon, color: arcLime, size: 26),
                                  const Spacer(),
                                  const Icon(
                                    Icons.north_east,
                                    size: 18,
                                    color: Colors.white54,
                                  ),
                                ],
                              ),
                              const SizedBox(height: 22),
                              Text(
                                d.name,
                                style: const TextStyle(
                                  fontSize: 22,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 10),
                              Text(
                                d.description,
                                style: const TextStyle(
                                  color: Colors.white60,
                                  height: 1.6,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
          const SizedBox(height: 24),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              OutlinedButton.icon(
                onPressed: onAllModels,
                icon: const Icon(Icons.view_module_outlined),
                label: const Text('Browse all AI models'),
              ),
              OutlinedButton.icon(
                onPressed: onEmployee,
                icon: const Icon(Icons.person_add_alt),
                label: const Text('Add my employee'),
              ),
              TextButton.icon(
                onPressed: onOffer,
                icon: const Icon(Icons.north_east),
                label: const Text('Offer your skills'),
              ),
            ],
          ),
        ],
      );
    },
  );
}

class MarketSupplierPicker extends StatelessWidget {
  const MarketSupplierPicker({
    super.key,
    required this.department,
    required this.onChoose,
    required this.onEmployee,
  });
  final MarketDepartment department;
  final ValueChanged<String> onChoose;
  final VoidCallback onEmployee;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, bounds) {
      final columns = bounds.maxWidth > 1000
          ? 3
          : bounds.maxWidth > 700
          ? 2
          : 1;
      final width = (bounds.maxWidth - (columns - 1) * 16) / columns;
      final cards = [
        ArcPathCard(
          eyebrow: 'INDIVIDUAL MODELS, REAL CAPABILITIES',
          title: 'AI models',
          description:
              'Compare specific model versions, their capabilities, context, and actual token rates.',
          icon: Icons.auto_awesome_outlined,
          color: arcLime,
          onTap: () => onChoose('ai'),
        ),
        ArcPathCard(
          eyebrow: 'DISCOVER AN INDEPENDENT SPECIALIST',
          title: 'Human talent',
          description:
              'Explore self-published profiles, experience, skills, rates, and availability.',
          icon: Icons.people_outline,
          color: arcLilac,
          onTap: () => onChoose('human'),
        ),
        ArcPathCard(
          eyebrow: 'THE PEOPLE YOU ALREADY TRUST',
          title: 'Your employees',
          description:
              'Add your own employees privately to this project. Their records never become marketplace listings.',
          icon: Icons.badge_outlined,
          color: const Color(0xFFFFD6A0),
          onTap: () => onChoose('employee'),
        ),
      ];
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            department.name,
            style: const TextStyle(
              color: arcLime,
              fontSize: 13,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Who should help\nbring it to life?',
            style: TextStyle(
              fontSize: 40,
              fontWeight: FontWeight.w600,
              height: 1.1,
            ),
          ),
          const SizedBox(height: 18),
          Text(
            department.description,
            style: const TextStyle(color: Colors.white60, height: 1.6),
          ),
          const SizedBox(height: 28),
          Wrap(
            spacing: 16,
            runSpacing: 16,
            children: cards
                .map((card) => SizedBox(width: width, child: card))
                .toList(),
          ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: onEmployee,
            icon: const Icon(Icons.person_add_alt),
            label: const Text('Add my employee'),
          ),
        ],
      );
    },
  );
}
