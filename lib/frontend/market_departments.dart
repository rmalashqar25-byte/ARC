import 'package:flutter/material.dart';

class MarketDepartment {
  const MarketDepartment(
    this.id,
    this.name,
    this.description,
    this.icon,
    this.roles,
  );
  final String id, name, description;
  final IconData icon;
  final List<String> roles;
}

const marketDepartments = [
  MarketDepartment(
    'research',
    'Research',
    'Find evidence, understand markets, and turn questions into insight.',
    Icons.travel_explore,
    ['market_researcher', 'marketing'],
  ),
  MarketDepartment(
    'it',
    'IT & engineering',
    'Build software, solve technical problems, and plan your infrastructure.',
    Icons.code_rounded,
    [
      'cto',
      'it',
      'app_developer',
      'cloud_engineer',
      'ai_engineer',
      'it_intern',
    ],
  ),
  MarketDepartment(
    'design',
    'Design & creative',
    'Shape a brand, explore visual ideas, and create better experiences.',
    Icons.palette_outlined,
    ['content_marketer', 'app_developer', 'marketing'],
  ),
  MarketDepartment(
    'marketing',
    'Marketing & sales',
    'Tell your story, reach customers, and build a growth plan.',
    Icons.campaign_outlined,
    ['marketing', 'content_marketer', 'sales_specialist', 'market_researcher'],
  ),
  MarketDepartment(
    'finance',
    'Finance & analysis',
    'Work through budgets, forecasts, and the numbers behind decisions.',
    Icons.insights_rounded,
    ['finance', 'accountant', 'financial_analyst'],
  ),
  MarketDepartment(
    'operations',
    'Operations',
    'Organize delivery, processes, milestones, and day-to-day work.',
    Icons.account_tree_outlined,
    ['manager', 'project_manager', 'operations_analyst', 'executive_assistant'],
  ),
  MarketDepartment(
    'legal',
    'Legal & compliance',
    'Prepare document reviews and questions for qualified legal review.',
    Icons.balance_outlined,
    ['legal', 'contract_analyst', 'compliance_specialist'],
  ),
];

MarketDepartment? marketDepartment(String? id) {
  for (final department in marketDepartments) {
    if (department.id == id) return department;
  }
  return null;
}
