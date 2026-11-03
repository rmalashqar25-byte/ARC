import 'package:flutter/material.dart';
import 'arc_design.dart';
import 'company_api_client.dart';
import 'market_departments.dart';

String talentPrice(Map<String, dynamic> profile) {
  if (profile['pricing'] == 'volunteer') return 'Open to volunteer';
  final rate = (profile['rate'] as num?) ?? 0;
  final amount = rate == rate.roundToDouble()
      ? rate.toStringAsFixed(0)
      : rate.toStringAsFixed(2);
  final price =
      '\$$amount / ${profile['pricing'] == 'project' ? 'project' : 'hour'}';
  return profile['is_example'] == true ? '$price · Example rate' : price;
}

class TalentProfileEditor extends StatefulWidget {
  const TalentProfileEditor({
    super.key,
    required this.api,
    this.profile,
    this.employee = false,
    this.department = 'general',
    this.sessionId,
  });
  final CompanyApiClient api;
  final Map<String, dynamic>? profile;
  final bool employee;
  final String department;
  final String? sessionId;
  @override
  State<TalentProfileEditor> createState() => _TalentProfileEditorState();
}

class _TalentProfileEditorState extends State<TalentProfileEditor> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _name,
      _role,
      _summary,
      _skills,
      _rate,
      _capacity;
  late String _pricing, _availability, _specialty;
  bool _busy = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    final p = widget.profile ?? {};
    _name = TextEditingController(text: p['name'] as String? ?? '');
    _role = TextEditingController(text: p['role'] as String? ?? '');
    _summary = TextEditingController(text: p['summary'] as String? ?? '');
    _skills = TextEditingController(
      text: (p['skills'] as List? ?? []).join(', '),
    );
    _rate = TextEditingController(text: p['rate']?.toString() ?? '');
    _capacity = TextEditingController(
      text: (p['job_capacity'] ?? 3).toString(),
    );
    _pricing = p['pricing'] as String? ?? 'hour';
    _availability = p['availability'] as String? ?? 'available';
    _specialty = p['department'] as String? ?? widget.department;
  }

  @override
  void dispose() {
    for (final c in [_name, _role, _summary, _skills, _rate, _capacity]) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, dynamic> _values(bool published) => {
    'name': _name.text.trim(),
    'role': _role.text.trim(),
    'summary': _summary.text.trim(),
    'skills': _skills.text
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toSet()
        .toList(),
    'rate': _pricing == 'volunteer' ? 0 : double.tryParse(_rate.text) ?? 0,
    'pricing': _pricing,
    'availability': _availability,
    'job_capacity': int.tryParse(_capacity.text) ?? 3,
    'published': published,
    'department': _specialty,
  };

  Future<void> _save(bool published) async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.employee) {
        final values = _values(false)..remove('published');
        values['session_id'] = widget.sessionId ?? '';
        await widget.api.addPrivateEmployee(values);
      } else {
        await widget.api.saveTalentProfile(_values(published));
      }
      if (mounted) Navigator.pop(context, true);
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'Your changes have not been published. We couldn’t reach the talent service. Please retry.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _remove() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove your profile?'),
        content: const Text(
          'Your listing will disappear from the talent marketplace.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep profile'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await widget.api.deleteTalentProfile();
      if (mounted) Navigator.pop(context, true);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Could not remove your profile. Please retry.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _field(
    TextEditingController controller,
    String label,
    String hint, {
    int lines = 1,
    int max = 100,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 18),
    child: TextFormField(
      controller: controller,
      maxLines: lines,
      maxLength: max,
      onChanged: (_) => setState(() {}),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        counterText: '',
        filled: true,
        fillColor: arcPanel,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
      ),
      validator: (value) {
        final text = value?.trim() ?? '';
        if (text.isEmpty) return 'Please add your ${label.toLowerCase()}';
        if (controller == _summary && text.length < 20) {
          return 'Use at least 20 characters to describe your work';
        }
        if (controller == _skills) {
          final skills = text
              .split(',')
              .where((s) => s.trim().isNotEmpty)
              .toList();
          if (skills.length > 12 || skills.any((s) => s.trim().length > 40)) {
            return 'Add up to 12 skills, each under 40 characters';
          }
        }
        return null;
      },
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: arcCanvas,
    appBar: AppBar(
      backgroundColor: arcCanvas,
      title: Text(
        widget.employee
            ? 'Add your employee'
            : widget.profile == null
            ? 'Join the talent market'
            : 'Your talent profile',
      ),
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1060),
        child: LayoutBuilder(
          builder: (context, bounds) {
            final editor = Form(
              key: _form,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.employee
                        ? 'People you know.\nWork you trust.'
                        : 'Let your work\nspeak for you.',
                    style: TextStyle(
                      fontSize: 36,
                      fontWeight: FontWeight.w600,
                      height: 1.1,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    widget.employee
                        ? 'Record their role, skills, availability, and rate. Keep your existing team organized inside the project.'
                        : 'Introduce yourself, share what you do best, and set your own terms.',
                    style: TextStyle(color: Colors.white60, height: 1.5),
                  ),
                  const SizedBox(height: 30),
                  _field(_name, 'Display name', 'How should people know you?'),
                  _field(
                    _role,
                    'Professional headline',
                    'e.g. Product designer & brand storyteller',
                  ),
                  _field(
                    _summary,
                    'About you',
                    'What can you help a company create? Tell us about your experience and approach.',
                    lines: 4,
                    max: 1200,
                  ),
                  _field(
                    _skills,
                    'Skills',
                    'e.g. Flutter, UI design, Prototyping',
                    max: 490,
                  ),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    initialValue: _specialty,
                    decoration: const InputDecoration(labelText: 'Specialty'),
                    items: [
                      const DropdownMenuItem(
                        value: 'general',
                        child: Text('General / multiple specialties'),
                      ),
                      ...marketDepartments.map(
                        (d) =>
                            DropdownMenuItem(value: d.id, child: Text(d.name)),
                      ),
                    ],
                    onChanged: (value) => setState(() => _specialty = value!),
                  ),
                  const SizedBox(height: 20),
                  TextFormField(
                    controller: _capacity,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Maximum active jobs',
                      helperText:
                          '0–20 slots, including pending offers. Use 0 to stop new offers.',
                    ),
                    validator: (v) {
                      final n = int.tryParse(v ?? '');
                      return n == null || n < 0 || n > 20
                          ? 'Choose a job capacity from 0 to 20'
                          : null;
                    },
                  ),
                  const SizedBox(height: 20),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    initialValue: _availability,
                    decoration: const InputDecoration(
                      labelText: 'Availability',
                    ),
                    items: const [
                      DropdownMenuItem(
                        value: 'available',
                        child: Text('Available for work'),
                      ),
                      DropdownMenuItem(
                        value: 'limited',
                        child: Text('Limited availability'),
                      ),
                      DropdownMenuItem(
                        value: 'unavailable',
                        child: Text('Not taking new work'),
                      ),
                    ],
                    onChanged: (v) => setState(() => _availability = v!),
                  ),
                  const SizedBox(height: 20),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    initialValue: _pricing,
                    decoration: const InputDecoration(
                      labelText: 'How you price your work',
                    ),
                    items: const [
                      DropdownMenuItem(
                        value: 'hour',
                        child: Text('Hourly rate · USD'),
                      ),
                      DropdownMenuItem(
                        value: 'project',
                        child: Text('Starting project price · USD'),
                      ),
                      DropdownMenuItem(
                        value: 'volunteer',
                        child: Text('Volunteer · no charge'),
                      ),
                    ],
                    onChanged: (v) => setState(() => _pricing = v!),
                  ),
                  if (_pricing != 'volunteer')
                    Padding(
                      padding: const EdgeInsets.only(top: 20),
                      child: TextFormField(
                        controller: _rate,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        onChanged: (_) => setState(() {}),
                        decoration: const InputDecoration(
                          labelText: 'Your rate',
                          prefixText: '\$ ',
                        ),
                        validator: (v) {
                          final rate = double.tryParse(v ?? '');
                          return rate == null ||
                                  !rate.isFinite ||
                                  rate < 0 ||
                                  rate > 100000
                              ? 'Enter a valid rate between 0 and 100,000'
                              : null;
                        },
                      ),
                    ),
                  const SizedBox(height: 24),
                  Text(
                    widget.employee
                        ? 'This employee stays private to your workspace and project. Adding them does not publish a listing, send an invitation, or make a payment. You control their assignments and job capacity.'
                        : 'Publishing makes this profile visible to other ARC users. Use this browser to manage your profile. Paid terms are agreed directly; no payment is collected here.',
                    style: TextStyle(
                      color: Colors.white54,
                      fontSize: 12,
                      height: 1.5,
                    ),
                  ),
                  const SizedBox(height: 20),
                  if (_error != null) ...[
                    ArcNotice(message: _error!),
                    const SizedBox(height: 16),
                  ],
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: arcLime,
                          foregroundColor: Colors.black,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 24,
                            vertical: 20,
                          ),
                        ),
                        onPressed: _busy ? null : () => _save(true),
                        icon: const Icon(Icons.north_east),
                        label: Text(
                          _busy
                              ? 'Saving…'
                              : widget.employee
                              ? 'Add employee to project'
                              : 'Publish my profile',
                        ),
                      ),
                      if (widget.profile != null && !widget.employee)
                        OutlinedButton(
                          onPressed: _busy ? null : () => _save(false),
                          child: const Text('Pause listing'),
                        ),
                      if (widget.profile != null && !widget.employee)
                        TextButton(
                          onPressed: _busy ? null : _remove,
                          child: const Text('Remove profile'),
                        ),
                    ],
                  ),
                ],
              ),
            );
            final preview = Container(
              padding: const EdgeInsets.all(26),
              decoration: BoxDecoration(
                color: arcPanel,
                borderRadius: BorderRadius.circular(26),
                border: Border.all(color: const Color(0xFF354032)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'YOUR LIVE PREVIEW',
                    style: TextStyle(
                      color: arcLime,
                      fontSize: 11,
                      letterSpacing: 2,
                    ),
                  ),
                  const SizedBox(height: 24),
                  CircleAvatar(
                    radius: 28,
                    backgroundColor: arcLilac,
                    child: Text(
                      _name.text.trim().isEmpty
                          ? 'Y'
                          : _name.text.trim().characters.first.toUpperCase(),
                      style: const TextStyle(color: Colors.black, fontSize: 24),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    _name.text.isEmpty ? 'Your name' : _name.text,
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _role.text.isEmpty
                        ? 'Your professional headline'
                        : _role.text,
                    style: const TextStyle(color: arcLilac),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    _summary.text.isEmpty
                        ? 'A little about your craft, your experience, and what you can bring to a team.'
                        : _summary.text,
                    maxLines: 8,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white60, height: 1.6),
                  ),
                  const SizedBox(height: 20),
                  Text(
                    talentPrice(_values(true)),
                    style: const TextStyle(color: arcLime, fontSize: 20),
                  ),
                ],
              ),
            );
            return SingleChildScrollView(
              padding: EdgeInsets.all(bounds.maxWidth < 650 ? 20 : 40),
              child: bounds.maxWidth >= 850
                  ? Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: editor),
                        const SizedBox(width: 42),
                        SizedBox(width: 310, child: preview),
                      ],
                    )
                  : Column(
                      children: [editor, const SizedBox(height: 30), preview],
                    ),
            );
          },
        ),
      ),
    ),
  );
}
