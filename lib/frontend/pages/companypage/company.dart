import 'package:arc/frontend/pages/companypage/company_dashboard.dart';
import 'package:arc/api_config.dart';
import 'package:flutter/material.dart';

class Company extends StatefulWidget {
  const Company({super.key, this.initialSessionId});

  final String? initialSessionId;

  @override
  State<Company> createState() => _CompanyState();
}

class _CompanyState extends State<Company> {
  @override
  Widget build(BuildContext context) {
    return CompanyDashboard(
      initialSessionId: widget.initialSessionId ?? ApiConfig.companySessionId,
    );
  }
}
