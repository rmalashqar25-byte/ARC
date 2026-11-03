# ARC Company backend

The mobile client talks only to `POST /company/ceo/run`.

Each CEO-to-director delegation creates or reuses a in-memory session group. A
director can add only its own direct-report employees to that group. Internal
tasks and reports are recorded as a user-scoped, read-only transcript:

- `GET /company/sessions/{session_id}/groups`
- `GET /company/sessions/{session_id}/events?after_id=0`
- `GET /company/sessions/{session_id}/stream?after_id=0` (Server-Sent Events)

The frontend may render these conversations, but it cannot post as a director
or employee. `POST /company/agents/{agent_id}/run` rejects every internal agent;
the CEO remains the only public company entry point.

The CEO uses Google AI Studio (`GEMINI_API_KEY`, `GEMINI_CEO_MODEL`) and may
delegate only to direct reports:

- CTO
- Operations Manager
- Marketing Director
- Finance Director
- Legal Director

Each lead uses OpenRouter and may delegate only to employees defined in its own
module. Employees cannot delegate further. `organization.py` is the source of
truth for reporting lines, while `agent_tools.py` validates every internal
delegation before it runs.

Department modules:

- `it.py`: CTO, IT engineer, cloud engineer, AI engineer, app developer, intern
- `management.py`: manager, project manager, operations analyst, assistant
- `marketing.py`: director, researcher, content, sales, and intern roles
- `finance.py`: director, accountant, and financial analyst
- `legal.py`: director, contract analyst, and compliance specialist

All OpenRouter agents receive the shared tool catalog. Low-risk tools may run
immediately; privileged tools remain controlled by the session owner's
allow, ask, or deny policy. The CEO cannot bypass those policies by delegating.
