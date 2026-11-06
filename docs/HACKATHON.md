# Hackathon requirements audit

Reviewed 6 November 2026 for **Vultr: Agent Rush / Powering the Future of Work (Challenge 2)**. This is an engineering checklist, not organizer certification or a guarantee of a prize.

## Requirements and evidence

| Item | Result |
| --- | --- |
| Public product-style web app and central backend on Vultr | Deployed in Atlanta; see [Vultr architecture](VULTR.md). HTTPS/API boundary checks passed. |
| Original project, MIT-compliant source | Root [MIT license](../LICENSE), dependency notices, and [provenance disclosure](../PROVENANCE.md). Existing ARC foundations are explicitly disclosed. |
| Public source and setup instructions | [GitHub](https://github.com/rmalashqar25-byte/ARC), root README and deployment guide. |
| Submission title, descriptions, tags and live URL | [Submitted entry](https://lablab.build/ai-hackathons/vultr-hackathon/arc1/arc-your-company-workspace). |
| MP4 video, PDF slides, cover | Existing ARC promo, 10-page PDF deck and cover uploaded. Promo is not a full technical walkthrough. |
| Serverless Inference | Optional for Challenge 2; not used or claimed. Challenge 1 is not claimed. |
| Automated verification | 157 backend tests, 41 Flutter tests and 10 tool/deployment tests passed. These suites include simulated provider responses; they are not all live model tests. |
| Real execution containment | Four real isolation checks, timeout/cleanup and a backend terminal RPC passed on Vultr. |
| Fully delegated live coding task | [Vultr evidence](evidence/vultr-company-task.json): a real eight-call free-model workflow delegated, changed the implementation, preserved tests and passed an independent container test. The previous model timed out safely. |
| External connectors | Finance, CRM and external cloud accounts are unconfigured. GitHub repository connection and the restricted owner terminal were verified. |
| Personal/team eligibility | Account owner must satisfy the platform eligibility rules, registrations, rights to media and any organizer decisions about reuse. These cannot be established by source-code tests. |

## Public-entry comparison

These are observations of public descriptions, not independent audits, scores or a prediction of judging results. No competitor application was attacked or tested.

- [YAI Guard](https://lablab.build/ai-hackathons/vultr-hackathon/yai-guard/yai-guard-prove-it-code-runner) describes a focused code runner with an offline-verifiable trace and cleanup verification. It presents execution evidence more concretely than ARC's promo.
- [JARVIS ProofOps](https://lablab.build/ai-hackathons/vultr-hackathon/jarvis-proofops/jarvis-proofops) describes commerce QA with expected versus observed outcomes and explicit limitations. ARC should match that clarity when reporting task results.
- [QuantGate](https://lablab.build/ai-hackathons/vultr-hackathon/wataruakis/quantgate) describes a bounded evaluation workflow, measured results and an independent reference. Its narrow demonstration is easier to assess than a broad company platform.
- ARC's distinction is the founder-to-manager-to-worker workflow, human capacity and restricted deliverable portal, plus a quiet deterministic scheduler. Its larger scope increases verification effort. It should lead with one reliable end-to-end workflow rather than promise every business integration.

**Assessment:** there is no defensible evidence that ARC is currently number one. Votes are community reactions, not judges' scores. Stronger task reliability, a technical walkthrough and measured pilot outcomes would improve its case. No customer adoption, saved-hours claim, revenue or security certification is invented.

## Official references

- [Event and challenge requirements](https://lablab.build/ai-hackathons/vultr-hackathon)
- [Rule book](https://lablab.build/hackathon-rules)
- [Submission guide](https://lablab.build/delivering-your-hackathon-solution)
- [Terms](https://lablab.build/terms-of-use)

The event page/form takes priority over generic guidance. A code license does not prove personal eligibility or rights to every external media asset. The existing promo remains the user's chosen submission video.
