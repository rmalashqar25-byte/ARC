# Review ARC in four minutes

**Challenge: Powering the Future of Work (Challenge 2).** [Live ARC](https://arc.64.177.59.174.sslip.io/) runs on Vultr, including the central Python planner, SQLite workflow queue and private execution service.

1. Open the live app and start a fresh company conversation. Ask the CEO what ARC can do. This is a live model call, not a prerecorded reply. Provider delays or quota limits can affect timing.
2. Open Create Company / the team marketplace. Choose a department, then AI agents or human talent. Model details show capabilities and prices separately from demo role pricing. A fictional sample human is labelled and cannot be hired.
3. Open Company work. Add a bounded assignment, assign a manager or employee, and inspect status/result. The scheduler runs every five seconds while the backend is up. Idle checks do not call a model; model generation and task execution take additional time. The public demo does not grant new anonymous workspaces the owner's terminal.
4. Add your own employee with a capacity. Create a job for that employee and issue a revocable invitation. Open it in a separate private browser. The human can see their own group/jobs, accept or decline and submit a result; they cannot browse internal agent chat. The founder/manager reviews it. Use fictional data and do not share invitation links publicly.
5. In Workspace settings, inspect Developer connections and Open-source licenses. A user's saved provider applies to all company roles. Changing it pauses automatic work. API secrets stay on the backend.

## Real execution evidence

[A real delegated task passed on Vultr](evidence/vultr-company-task.json) using `cohere/north-mini-code:free`, with eight provider requests, all reporting zero cost. The isolated code workflow requires an explicitly paired workspace. See docs/VULTR.md and the published evidence for what was actually run, the model and environment, rather than assuming a chat promise means success. `tools/verify_free_agent.py` seeds a failing discount test, routes an actual task through CEO and the queue, verifies the agent changed the implementation without changing the test, and independently reruns it. It stops after a bounded number of free-model calls and never edits the live company's approvals.

The submitted video is the team's existing promotional video, accompanied by PDF slides. It is not a technical recording of every feature. Repository evidence and the interactive product provide additional verification. No fabricated customers, ROI, live hiring, payments, or automatic GitHub publication are claimed.
