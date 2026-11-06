import 'dart:convert';
import 'package:arc/api_config.dart';
import 'package:arc/frontend/arc_design.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const _muted = Color(0xFFA7B0A5);

class DeveloperSettingsPage extends StatefulWidget {
  const DeveloperSettingsPage({super.key, this.client});
  final http.Client? client;

  @override
  State<DeveloperSettingsPage> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<DeveloperSettingsPage> {
  late final http.Client _client = widget.client ?? http.Client();
  final _form = GlobalKey<FormState>();
  final _model = TextEditingController();
  final _address = TextEditingController();
  final _key = TextEditingController();
  String _provider = 'openrouter';
  String? _savedProvider;
  String? _message;
  bool _loading = true;
  bool _busy = false;
  bool _localAvailable = false;
  bool _tools = true;
  bool _usage = false;
  bool _hasConnection = false;
  List<Map<String, String>> _models = [];
  String _modelName = '';

  bool get _local =>
      _provider == 'ollama' ||
      _provider == 'vultr_model' ||
      (_provider == 'custom' && _address.text.trim().startsWith('http://'));

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<Map<String, dynamic>> _request(
    String path,
    String method, [
    Map<String, dynamic>? body,
  ]) async {
    final uri = ApiConfig.endpoint('/developer/$path');
    final headers = {
      ...ApiConfig.headers(),
      'Content-Type': 'application/json',
    };
    final response =
        await (method == 'PUT'
                ? _client.put(uri, headers: headers, body: jsonEncode(body))
                : method == 'POST'
                ? _client.post(uri, headers: headers, body: jsonEncode(body))
                : method == 'DELETE'
                ? _client.delete(uri, headers: headers)
                : _client.get(uri, headers: headers))
            .timeout(const Duration(seconds: 24));
    if (response.statusCode >= 300) {
      throw StateError(
        response.statusCode == 401
            ? 'Your provider rejected that API key. Check it and try again.'
            : method == 'POST'
            ? 'Could not list models. Check your key, API address, and model server.'
            : 'Could not save the connection. Check the fields and try again.',
      );
    }
    return Map<String, dynamic>.from(jsonDecode(response.body) as Map);
  }

  Future<void> _load() async {
    try {
      final data = await _request('connection', 'GET');
      if (!mounted) return;
      final saved = Map<String, dynamic>.from(data['connection'] as Map? ?? {});
      setState(() {
        _localAvailable = data['local_available'] == true;
        _hasConnection = saved.isNotEmpty;
        _message = null;
        _savedProvider = saved['provider'] as String?;
        _provider = _savedProvider ?? 'openrouter';
        _model.text = saved['model'] as String? ?? '';
        _modelName = saved['model_name'] as String? ?? _model.text;
        _address.text = saved['base_url'] as String? ?? '';
        _tools = saved['supports_tools'] != false;
        _usage = saved['confirm_usage'] == true;
      });
    } catch (_) {
      if (mounted) {
        setState(
          () => _message = 'Your connection could not be loaded. Try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submit({bool discover = false}) async {
    if (_busy || !(_form.currentState?.validate() ?? false)) return;
    if (!discover && !_local && !_usage) {
      setState(() => _message = 'Confirm your provider’s usage charges first.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final body = {
        'provider': _provider,
        'model': _model.text.trim(),
        'model_name': _modelName,
        'base_url': _address.text.trim(),
        'api_key': _key.text.trim(),
        'supports_tools': _tools,
        'confirm_usage': _usage,
      };
      if (!discover && _model.text.trim().isEmpty) {
        setState(
          () => _message = 'Load the available models and choose one first.',
        );
        return;
      }
      final result = await _request(
        discover ? 'models' : 'connection',
        discover ? 'POST' : 'PUT',
        body,
      );
      if (!mounted) return;
      setState(() {
        if (discover) {
          _models = (result['models'] as List)
              .whereType<Map>()
              .map(
                (m) => {'id': m['id'].toString(), 'name': m['name'].toString()},
              )
              .toList();
          if (!_models.any((m) => m['id'] == _model.text)) {
            _model.clear();
            _modelName = '';
          }
          if (_provider == 'vultr_model' && _models.length == 1) {
            _model.text = _models.first['id']!;
            _modelName = _models.first['name']!;
          }
          _message = _models.isEmpty
              ? 'Connected, but no models were listed. Check your provider or local model installation.'
              : 'Connected. Choose from ${_models.length} models.';
        } else {
          _key.clear();
          _hasConnection = true;
          _savedProvider = _provider;
          _message =
              'Connection saved. Your CEO and team will use this model. Company work is paused; start it when ready.';
        }
      });
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is StateError
              ? error.message.toString()
              : 'Could not reach your connection. Try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _remove() async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await _request('connection', 'DELETE');
      if (!mounted) return;
      _key.clear();
      _model.clear();
      setState(() {
        _hasConnection = false;
        _savedProvider = null;
        _message =
            'Your connection was removed. Company work is paused. ARC’s default connection will be used for new chats.';
      });
    } catch (_) {
      if (mounted) {
        setState(
          () => _message = 'Could not remove the connection. Try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _model.dispose();
    _address.dispose();
    _key.dispose();
    if (widget.client == null) _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Theme(
    data: Theme.of(context).copyWith(
      colorScheme: ColorScheme.fromSeed(
        seedColor: arcLime,
        brightness: Brightness.dark,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: arcPanel,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 18,
          vertical: 20,
        ),
        labelStyle: const TextStyle(color: _muted),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Color(0xFF313A32)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: arcLime),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: arcLime,
          side: const BorderSide(color: Color(0xFF394633)),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),
    ),
    child: Scaffold(
      backgroundColor: arcCanvas,
      appBar: AppBar(
        title: const Text('Developer connections'),
        backgroundColor: arcCanvas,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 740),
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: _ConnectionMark(),
                    ),
                    const SizedBox(height: 18),
                    const Text(
                      'Your workspace.\nYour way.',
                      style: TextStyle(
                        fontSize: 36,
                        fontWeight: FontWeight.w700,
                        height: 1.15,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 14),
                    const Text(
                      'Connect your own provider or run a model locally. This connection replaces ARC’s default API for your CEO and every company role.',
                      style: TextStyle(color: _muted, height: 1.6),
                    ),
                    const SizedBox(height: 26),
                    Form(
                      key: _form,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          DropdownButtonFormField<String>(
                            initialValue: _provider,
                            isExpanded: true,
                            decoration: const InputDecoration(
                              labelText: 'Provider',
                              border: OutlineInputBorder(),
                            ),
                            items: const [
                              DropdownMenuItem(
                                value: 'openai',
                                child: Text('OpenAI API'),
                              ),
                              DropdownMenuItem(
                                value: 'openrouter',
                                child: Text('OpenRouter'),
                              ),
                              DropdownMenuItem(
                                value: 'vultr',
                                child: Text('Vultr Serverless Inference'),
                              ),
                              DropdownMenuItem(
                                value: 'vultr_model',
                                child: Text('Vultr Cloud Model'),
                              ),
                              DropdownMenuItem(
                                value: 'gemini',
                                child: Text('Gemini API'),
                              ),
                              DropdownMenuItem(
                                value: 'ollama',
                                child: Text('Ollama · local models'),
                              ),
                              DropdownMenuItem(
                                value: 'custom',
                                child: Text('Custom · OpenAI-compatible API'),
                              ),
                            ],
                            onChanged: _busy
                                ? null
                                : (value) => setState(() {
                                    _provider = value!;
                                    _models = [];
                                    _model.clear();
                                    _key.clear();
                                    _usage = false;
                                    _address.text = value == 'custom'
                                        ? 'https://'
                                        : '';
                                    _message = null;
                                  }),
                          ),
                          const SizedBox(height: 18),
                          if (_provider == 'vultr_model') ...[
                            const Text(
                              'Qwen runs on ARC’s dedicated Vultr server. No API key is needed. Server hosting charges apply, with no per-token provider fee. This connection powers your CEO and every company role. CPU replies can take longer.',
                              style: TextStyle(color: _muted, height: 1.5),
                            ),
                            const SizedBox(height: 18),
                          ],
                          if (_provider == 'vultr') ...[
                            const Text(
                              'Connect your Vultr Serverless Inference subscription. No extra model server is needed. Vultr bills token usage; available promotional credits depend on your account. Your chosen model is used by the CEO and every company role.',
                              style: TextStyle(color: _muted, height: 1.5),
                            ),
                            const SizedBox(height: 18),
                          ],
                          if (_provider == 'ollama') ...[
                            Text(
                              _localAvailable
                                  ? 'Runs through Ollama on this computer at localhost:11434. Start Ollama and install a model first, then load the available models. Llama is one model family you can run with Ollama.'
                                  : 'Local Ollama needs ARC running on your computer with the local launcher.',
                              style: const TextStyle(
                                color: _muted,
                                height: 1.5,
                              ),
                            ),
                            const SizedBox(height: 18),
                          ],
                          if (_provider == 'custom') ...[
                            TextFormField(
                              controller: _address,
                              enabled: !_busy,
                              decoration: const InputDecoration(
                                labelText: 'API base URL',
                                hintText: 'https://your-provider.example/v1',
                                border: OutlineInputBorder(),
                              ),
                              onChanged: (_) => setState(() {}),
                              validator: (v) =>
                                  Uri.tryParse(v?.trim() ?? '')?.hasAuthority ==
                                      true
                                  ? null
                                  : 'Enter a full API base URL',
                            ),
                            const SizedBox(height: 10),
                            const Text(
                              'Use a Chat Completions API. Local llama.cpp (port 8080) and LM Studio (port 1234) can use http://127.0.0.1:PORT/v1 with ARC’s local launcher.',
                              style: TextStyle(
                                color: _muted,
                                height: 1.5,
                                fontSize: 12,
                              ),
                            ),
                            const SizedBox(height: 18),
                          ],
                          if (!_local) ...[
                            TextFormField(
                              controller: _key,
                              enabled: !_busy,
                              obscureText: true,
                              enableSuggestions: false,
                              autocorrect: false,
                              decoration: InputDecoration(
                                labelText: 'API key',
                                hintText:
                                    _hasConnection &&
                                        _savedProvider == _provider
                                    ? 'Leave blank to keep the saved key'
                                    : 'Paste your provider API key',
                                border: const OutlineInputBorder(),
                              ),
                              validator: (v) =>
                                  (v?.trim().isNotEmpty ?? false) ||
                                      (_hasConnection &&
                                          _savedProvider == _provider)
                                  ? null
                                  : 'Enter your API key',
                            ),
                            const SizedBox(height: 10),
                            const Text(
                              'Saved encrypted on the ARC server. Never included in agent messages or browser storage.',
                              style: TextStyle(
                                color: _muted,
                                fontSize: 12,
                                height: 1.5,
                              ),
                            ),
                            const SizedBox(height: 18),
                          ],
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Text(
                                'YOUR MODEL',
                                style: TextStyle(
                                  color: arcLime,
                                  letterSpacing: 2,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 12),
                              OutlinedButton.icon(
                                style: OutlinedButton.styleFrom(
                                  padding: const EdgeInsets.all(18),
                                  alignment: Alignment.centerLeft,
                                ),
                                onPressed: _busy || _models.isEmpty
                                    ? null
                                    : () async {
                                        final selected =
                                            await showSearch<String>(
                                              context: context,
                                              delegate: _ModelSearch(_models),
                                            );
                                        if (selected != null &&
                                            selected.isNotEmpty &&
                                            mounted) {
                                          setState(() {
                                            _model.text = selected;
                                            _modelName = _models.firstWhere(
                                              (m) => m['id'] == selected,
                                            )['name']!;
                                          });
                                        }
                                      },
                                icon: const Icon(Icons.smart_toy_outlined),
                                label: Text(
                                  _model.text.isEmpty
                                      ? 'Choose a model'
                                      : _modelName,
                                ),
                              ),
                              const SizedBox(height: 12),
                              OutlinedButton.icon(
                                onPressed:
                                    _busy ||
                                        (_provider == 'ollama' &&
                                            !_localAvailable)
                                    ? null
                                    : () => _submit(discover: true),
                                icon: const Icon(Icons.sync_rounded),
                                label: const Text('Load available models'),
                              ),
                              const SizedBox(height: 10),
                              const Text(
                                'Load your provider’s models, then choose by name. No model ID to type. This check does not generate an AI reply.',
                                style: TextStyle(
                                  color: _muted,
                                  fontSize: 12,
                                  height: 1.5,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          CheckboxListTile(
                            contentPadding: EdgeInsets.zero,
                            value: _tools,
                            onChanged: _busy
                                ? null
                                : (v) => setState(() => _tools = v!),
                            title: const Text(
                              'This model supports tool calling',
                            ),
                            subtitle: const Text(
                              'Required for company agents to edit files and run checks. Turn off for chat and planning only.',
                            ),
                          ),
                          if (!_local)
                            CheckboxListTile(
                              contentPadding: EdgeInsets.zero,
                              value: _usage,
                              onChanged: _busy
                                  ? null
                                  : (v) => setState(() => _usage = v!),
                              title: const Text(
                                'Use my provider account and its usage pricing',
                              ),
                              subtitle: const Text(
                                'ARC does not pay these API charges. Automatic work keeps its 36 model requests per day limit.',
                              ),
                            ),
                          const SizedBox(height: 18),
                          if (_busy) const LinearProgressIndicator(),
                          if (_message != null)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 18),
                              child: Text(
                                _message!,
                                style: const TextStyle(
                                  color: arcLime,
                                  height: 1.5,
                                ),
                              ),
                            ),
                          FilledButton.icon(
                            style: FilledButton.styleFrom(
                              backgroundColor: arcLime,
                              foregroundColor: arcCanvas,
                              padding: const EdgeInsets.all(18),
                            ),
                            onPressed:
                                _busy ||
                                    (_provider == 'ollama' && !_localAvailable)
                                ? null
                                : _submit,
                            icon: const Icon(Icons.link_rounded),
                            label: const Text('Save my connection'),
                          ),
                          if (_hasConnection)
                            TextButton(
                              onPressed: _busy ? null : _remove,
                              child: const Text('Remove my connection'),
                            ),
                          const SizedBox(height: 30),
                          const Text(
                            'Local terminal',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            'ARC’s local launcher starts the installed terminal and connects your workspace automatically. No connection code to type. Agents keep their project scope and restricted commands.',
                            style: TextStyle(color: _muted, height: 1.5),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
    ),
  );
}

class _ModelSearch extends SearchDelegate<String> {
  _ModelSearch(this.models);
  final List<Map<String, String>> models;
  @override
  List<Widget> buildActions(BuildContext context) => [
    IconButton(onPressed: () => query = '', icon: const Icon(Icons.clear)),
  ];
  @override
  Widget buildLeading(BuildContext context) => IconButton(
    onPressed: () => close(context, ''),
    icon: const Icon(Icons.arrow_back),
  );
  @override
  Widget buildResults(BuildContext context) => buildSuggestions(context);
  @override
  Widget buildSuggestions(BuildContext context) {
    final matching = models
        .where((m) => m['name']!.toLowerCase().contains(query.toLowerCase()))
        .toList();
    return ListView.builder(
      itemCount: matching.length,
      itemBuilder: (context, index) => ListTile(
        title: Text(matching[index]['name']!),
        onTap: () => close(context, matching[index]['id']!),
      ),
    );
  }
}

class _ConnectionMark extends StatelessWidget {
  const _ConnectionMark();
  @override
  Widget build(BuildContext context) => Container(
    width: 62,
    height: 62,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(20),
      gradient: const LinearGradient(
        colors: [Color(0xFF2B3C25), Color(0xFF19221B)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      border: Border.all(color: const Color(0xFF44553A)),
    ),
    child: const Icon(Icons.tune_rounded, color: arcLime, size: 30),
  );
}
