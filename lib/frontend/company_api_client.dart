import 'dart:async';
import 'dart:convert';

import 'package:arc/api_config.dart';
import 'user_messages.dart';
import 'package:http/http.dart' as http;

typedef CompanyAccessTokenProvider = Future<String?> Function();

class CompanyApiException implements Exception {
  const CompanyApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class CompanyAgent {
  const CompanyAgent({
    required this.id,
    required this.name,
    required this.jobTitle,
    required this.department,
    required this.purpose,
    required this.provider,
    required this.reportsTo,
  });

  factory CompanyAgent.fromJson(Map<dynamic, dynamic> json) {
    return CompanyAgent(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Agent',
      jobTitle: json['job_title']?.toString() ?? '',
      department: json['department']?.toString() ?? '',
      purpose: json['purpose']?.toString() ?? '',
      provider: json['provider']?.toString() ?? '',
      reportsTo: json['reports_to']?.toString(),
    );
  }

  final String id;
  final String name;
  final String jobTitle;
  final String department;
  final String purpose;
  final String provider;
  final String? reportsTo;
}

class CompanyCatalog {
  const CompanyCatalog({required this.agents});

  factory CompanyCatalog.fromJson(Map<dynamic, dynamic> json) {
    final rawAgents = json['agents'];
    return CompanyCatalog(
      agents: rawAgents is List
          ? rawAgents.whereType<Map>().map(CompanyAgent.fromJson).toList()
          : const [],
    );
  }

  final List<CompanyAgent> agents;

  CompanyAgent? agent(String id) {
    for (final agent in agents) {
      if (agent.id == id) return agent;
    }
    return null;
  }
}

class HumanEmployee {
  const HumanEmployee({
    required this.id,
    required this.name,
    required this.role,
  });

  factory HumanEmployee.fromJson(Map<dynamic, dynamic> json) => HumanEmployee(
    id: json['id']?.toString() ?? '',
    name: json['name']?.toString() ?? '',
    role: json['role']?.toString() ?? '',
  );

  final String id;
  final String name;
  final String role;
}

class CompanyMember {
  const CompanyMember({
    required this.agentId,
    required this.role,
    required this.addedBy,
    this.displayName,
  });

  factory CompanyMember.fromJson(Map<dynamic, dynamic> json) {
    return CompanyMember(
      agentId: json['agent_id']?.toString() ?? '',
      role: json['membership_role']?.toString() ?? 'employee',
      addedBy: json['added_by']?.toString() ?? '',
      displayName: json['display_name']?.toString(),
    );
  }

  final String agentId;
  final String role;
  final String addedBy;
  final String? displayName;
}

class CompanyGroup {
  const CompanyGroup({
    required this.id,
    required this.name,
    required this.directorId,
    required this.objective,
    required this.status,
    required this.members,
  });

  factory CompanyGroup.fromJson(Map<dynamic, dynamic> json) {
    final rawMembers = json['members'];
    return CompanyGroup(
      id: json['group_id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Company group',
      directorId: json['director_id']?.toString() ?? '',
      objective: json['objective']?.toString() ?? '',
      status: json['status']?.toString() ?? 'active',
      members: rawMembers is List
          ? rawMembers.whereType<Map>().map(CompanyMember.fromJson).toList()
          : const [],
    );
  }

  final String id;
  final String name;
  final String directorId;
  final String objective;
  final String status;
  final List<CompanyMember> members;
}

class CompanyEvent {
  const CompanyEvent({
    required this.id,
    required this.sessionId,
    required this.groupId,
    required this.senderId,
    required this.recipientId,
    required this.type,
    required this.content,
    required this.metadata,
    required this.createdAt,
  });

  factory CompanyEvent.fromJson(Map<dynamic, dynamic> json) {
    return CompanyEvent(
      id: int.tryParse(json['id']?.toString() ?? '') ?? 0,
      sessionId: json['session_id']?.toString() ?? '',
      groupId: json['group_id']?.toString(),
      senderId: json['sender_id']?.toString() ?? 'system',
      recipientId: json['recipient_id']?.toString() ?? '',
      type: json['event_type']?.toString() ?? 'event',
      content: json['content']?.toString() ?? '',
      metadata: json['metadata'] is Map
          ? Map<String, dynamic>.from(json['metadata'] as Map)
          : const {},
      createdAt: DateTime.fromMillisecondsSinceEpoch(
        (((json['created_at'] as num?)?.toDouble() ?? 0) * 1000).round(),
        isUtc: true,
      ).toLocal(),
    );
  }

  final int id;
  final String sessionId;
  final String? groupId;
  final String senderId;
  final String recipientId;
  final String type;
  final String content;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;
}

class CompanyApproval {
  const CompanyApproval({
    required this.id,
    required this.token,
    required this.tool,
    required this.role,
    required this.arguments,
    required this.expiresAt,
  });

  factory CompanyApproval.fromJson(Map<dynamic, dynamic> json) {
    return CompanyApproval(
      id: json['approval_id']?.toString() ?? '',
      token: json['approval_token']?.toString() ?? '',
      tool: json['tool']?.toString() ?? 'tool',
      role: json['role']?.toString() ?? 'agent',
      arguments: json['arguments'] is Map
          ? Map<String, dynamic>.from(json['arguments'] as Map)
          : const {},
      expiresAt: DateTime.tryParse(json['expires_at']?.toString() ?? ''),
    );
  }

  final String id;
  final String token;
  final String tool;
  final String role;
  final Map<String, dynamic> arguments;
  final DateTime? expiresAt;
}

class CompanyCeoResult {
  const CompanyCeoResult({
    required this.message,
    required this.groups,
    required this.events,
    required this.approvals,
  });

  factory CompanyCeoResult.fromJson(Map<dynamic, dynamic> json) {
    final rawGroups = json['groups'];
    final rawEvents = json['events'];
    final rawApprovals = json['pending_approvals'];
    return CompanyCeoResult(
      message: json['message']?.toString() ?? '',
      groups: rawGroups is List
          ? rawGroups.whereType<Map>().map(CompanyGroup.fromJson).toList()
          : const [],
      events: rawEvents is List
          ? rawEvents.whereType<Map>().map(CompanyEvent.fromJson).toList()
          : const [],
      approvals: rawApprovals is List
          ? rawApprovals
                .whereType<Map>()
                .map(CompanyApproval.fromJson)
                .where((approval) => approval.id.isNotEmpty)
                .toList()
          : const [],
    );
  }

  final String message;
  final List<CompanyGroup> groups;
  final List<CompanyEvent> events;
  final List<CompanyApproval> approvals;
}

class CompanyEventsPage {
  const CompanyEventsPage({required this.events, required this.nextAfterId});

  final List<CompanyEvent> events;
  final int nextAfterId;
}

class CompanyApiClient {
  CompanyApiClient({http.Client? client, this.accessTokenProvider})
    : _client = client ?? http.Client(),
      _ownsClient = client == null;

  final http.Client _client;
  final bool _ownsClient;
  final CompanyAccessTokenProvider? accessTokenProvider;

  Future<String?> _accessToken() async {
    if (accessTokenProvider != null) return accessTokenProvider!.call();
    return ApiConfig.sessionToken;
  }

  Future<Map<String, String>> _headers({bool jsonBody = false}) async {
    final token = await _accessToken();
    if (token == null || token.isEmpty) {
      throw const CompanyApiException(
        'Temporary session is unavailable. Restart the app.',
      );
    }
    return {
      'X-Arc-Session': token,
      if (jsonBody) 'Content-Type': 'application/json',
    };
  }

  Future<CompanyCatalog> loadCatalog() async {
    final response = await _client
        .get(ApiConfig.endpoint('/company/catalog'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    return CompanyCatalog.fromJson(_decodeResponse(response));
  }

  Future<String> loadApprovalMode() async {
    final response = await _client
        .get(
          ApiConfig.endpoint('/company/approval-policy'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 20));
    return _decodeResponse(response)['mode']?.toString() ?? 'ask';
  }

  Future<String> saveApprovalMode(String mode) async {
    final response = await _client
        .put(
          ApiConfig.endpoint('/company/approval-policy'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'mode': mode,
            'confirm_automatic_access': mode == 'allow',
          }),
        )
        .timeout(const Duration(seconds: 20));
    return _decodeResponse(response)['mode']?.toString() ?? 'ask';
  }

  Future<List<Map<String, dynamic>>> loadApprovalRequests() async {
    final response = await _client
        .get(
          ApiConfig.endpoint('/company/approval-requests'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 20));
    final items = _decodeResponse(response)['requests'];
    return items is List
        ? items
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
        : const [];
  }

  Future<Map<String, dynamic>> decideApprovalRequest({
    required String id,
    required String sessionId,
    required bool approve,
  }) async {
    final response = await _client
        .post(
          ApiConfig.endpoint(
            '/company/approval-requests/${Uri.encodeComponent(id)}',
          ),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'session_id': sessionId, 'approve': approve}),
        )
        .timeout(const Duration(minutes: 2));
    return _decodeResponse(response);
  }

  Future<List<Map<String, dynamic>>> loadOwnEmployees(String sessionId) async {
    final response = await _client
        .get(
          ApiConfig.endpoint('/company/humans', {'session_id': sessionId}),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 15));
    return (_decodeResponse(response)['employees'] as List)
        .map((p) => Map<String, dynamic>.from(p as Map))
        .toList();
  }

  Future<Map<String, dynamic>> addPrivateEmployee(
    Map<String, dynamic> employee,
  ) async {
    final response = await _client
        .post(
          ApiConfig.endpoint('/company/humans'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode(employee),
        )
        .timeout(const Duration(seconds: 15));
    return _decodeResponse(response);
  }

  Future<List<HumanEmployee>> loadHumans() async {
    final response = await _client
        .get(ApiConfig.endpoint('/company/humans'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    final items = _decodeResponse(response)['employees'];
    return items is List
        ? items.whereType<Map>().map(HumanEmployee.fromJson).toList()
        : const [];
  }

  Future<List<Map<String, dynamic>>> loadTalent() async {
    final response = await _client
        .get(ApiConfig.endpoint('/company/talent'), headers: await _headers())
        .timeout(const Duration(seconds: 15));
    return (_decodeResponse(response)['profiles'] as List)
        .map((p) => Map<String, dynamic>.from(p as Map))
        .toList();
  }

  Future<Map<String, dynamic>?> loadMyTalentProfile() async {
    final response = await _client
        .get(
          ApiConfig.endpoint('/company/talent/profile'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 15));
    final profile = _decodeResponse(response)['profile'];
    return profile is Map ? Map<String, dynamic>.from(profile) : null;
  }

  Future<Map<String, dynamic>> saveTalentProfile(
    Map<String, dynamic> profile,
  ) async {
    final response = await _client
        .put(
          ApiConfig.endpoint('/company/talent/profile'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode(profile),
        )
        .timeout(const Duration(seconds: 15));
    return _decodeResponse(response);
  }

  Future<void> deleteTalentProfile() async {
    final response = await _client
        .delete(
          ApiConfig.endpoint('/company/talent/profile'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 15));
    _decodeResponse(response);
  }

  Future<void> saveTalentBrief(
    String profileId,
    String sessionId,
    String brief,
  ) async {
    final response = await _client
        .post(
          ApiConfig.endpoint(
            '/company/talent/${Uri.encodeComponent(profileId)}/briefs',
          ),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'session_id': sessionId, 'description': brief}),
        )
        .timeout(const Duration(seconds: 15));
    _decodeResponse(response);
  }

  Future<HumanEmployee> addHuman({
    required String name,
    required String role,
  }) async {
    final response = await _client
        .post(
          ApiConfig.endpoint('/company/humans'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'name': name, 'role': role}),
        )
        .timeout(const Duration(seconds: 20));
    return HumanEmployee.fromJson(_decodeResponse(response));
  }

  Future<Map<String, dynamic>> assignHumanTask({
    required String employeeId,
    required String sessionId,
    required String description,
  }) async {
    final response = await _client
        .post(
          ApiConfig.endpoint('/company/human-tasks'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'employee_id': employeeId,
            'session_id': sessionId,
            'description': description,
          }),
        )
        .timeout(const Duration(seconds: 20));
    return _decodeResponse(response);
  }

  Future<List<CompanyGroup>> loadGroups(String sessionId) async {
    final response = await _client
        .get(
          ApiConfig.endpoint('/company/sessions/$sessionId/groups'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 20));
    final body = _decodeResponse(response);
    final groups = body['groups'];
    return groups is List
        ? groups.whereType<Map>().map(CompanyGroup.fromJson).toList()
        : const [];
  }

  Future<CompanyEventsPage> loadEvents(
    String sessionId, {
    int afterId = 0,
    int limit = 200,
  }) async {
    final response = await _client
        .get(
          ApiConfig.endpoint('/company/sessions/$sessionId/events', {
            'after_id': '$afterId',
            'limit': '$limit',
          }),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 20));
    final body = _decodeResponse(response);
    final rawEvents = body['events'];
    return CompanyEventsPage(
      events: rawEvents is List
          ? rawEvents.whereType<Map>().map(CompanyEvent.fromJson).toList()
          : const [],
      nextAfterId:
          int.tryParse(body['next_after_id']?.toString() ?? '') ?? afterId,
    );
  }

  Future<CompanyCeoResult> runCeo({
    required String prompt,
    required String sessionId,
  }) async {
    final response = await _client
        .post(
          ApiConfig.endpoint('/company/ceo/run'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'prompt': prompt, 'session_id': sessionId}),
        )
        .timeout(const Duration(minutes: 3));
    return CompanyCeoResult.fromJson(_decodeResponse(response));
  }

  Future<Map<String, dynamic>> loadProjectTeam(String sessionId) async {
    final response = await _client
        .get(
          ApiConfig.endpoint(
            '/company/sessions/${Uri.encodeComponent(sessionId)}/team',
          ),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 15));
    return _decodeResponse(response);
  }

  Future<Map<String, dynamic>> saveProjectTeam(
    String sessionId,
    String mode,
    List<Map<String, String>> members,
  ) async {
    final response = await _client
        .put(
          ApiConfig.endpoint(
            '/company/sessions/${Uri.encodeComponent(sessionId)}/team',
          ),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'mode': mode, 'members': members}),
        )
        .timeout(const Duration(seconds: 15));
    return _decodeResponse(response);
  }

  Future<List<Map<String, dynamic>>> loadMarketplace({
    bool refresh = false,
  }) async {
    final response = await _client
        .get(
          ApiConfig.endpoint(
            '/company/marketplace',
            refresh ? {'refresh': 'true'} : null,
          ),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 15));
    final body = _decodeResponse(response);
    return (body['agents'] as List)
        .map((a) => Map<String, dynamic>.from(a as Map))
        .toList();
  }

  Future<Map<String, dynamic>> decideApproval({
    required CompanyApproval approval,
    required String sessionId,
    required bool approve,
  }) async {
    final response = await _client
        .post(
          ApiConfig.endpoint('/company/approvals/${approval.id}'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'session_id': sessionId,
            'approval_token': approval.token,
            'approve': approve,
          }),
        )
        .timeout(const Duration(minutes: 2));
    return _decodeResponse(response);
  }

  Stream<CompanyEvent> watchEvents(String sessionId, {int afterId = 0}) async* {
    var cursor = afterId;
    while (true) {
      final request = http.Request(
        'GET',
        ApiConfig.endpoint('/company/sessions/$sessionId/stream', {
          'after_id': '$cursor',
        }),
      );
      request.headers.addAll(await _headers());
      final response = await _client.send(request);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final body = await response.stream.bytesToString();
        throw CompanyApiException(
          _errorMessage(body, response.statusCode),
          statusCode: response.statusCode,
        );
      }
      await for (final line
          in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (!line.startsWith('data:')) continue;
        final payload = line.substring(5).trim();
        if (payload.isEmpty) continue;
        final decoded = jsonDecode(payload);
        if (decoded is! Map) continue;
        final event = CompanyEvent.fromJson(decoded);
        if (event.id <= cursor) continue;
        cursor = event.id;
        yield event;
      }
      await Future<void>.delayed(const Duration(milliseconds: 1500));
    }
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    Map<String, dynamic> body = const {};
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map) body = Map<String, dynamic>.from(decoded);
    } catch (_) {
      // The status fallback below handles non-JSON server responses.
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw CompanyApiException(
        requestFailureMessage(response.statusCode),
        statusCode: response.statusCode,
      );
    }
    return body;
  }

  String _errorMessage(String responseBody, int statusCode) =>
      requestFailureMessage(statusCode);

  void close() {
    if (_ownsClient) _client.close();
  }
}
