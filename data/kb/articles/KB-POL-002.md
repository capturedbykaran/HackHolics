---
source_id: "KB-POL-002"
doc_type: "policy"
title: "Support escalation and response times"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-09-01"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_policy"
synthetic: "Y"
---
# Support escalation and response times

This policy defines the mandatory response time targets and the specific conditions under which support interactions are escalated from automated assistance to human agents. It applies to all CloudFlow customers using product versions 3.x and 4.x.

## Response targets

Support response times are determined by the issue category and the customer's active support plan. The following targets are binding:

*   Billing inquiries must be responded to within 1 business day (24 hours).
*   Security issues must be responded to within 4 hours.
*   Technical issues on priority support plans (Business, Enterprise) must be responded to within 8 hours.
*   Technical issues on standard support plans (Free, Pro) must be responded to within 24 hours.

## When we hand off to a person

Automated assistance is used for initial triage, but specific scenarios require immediate handoff to a human support agent. The following conditions mandate a handoff:

*   Requests for refunds, credits, billing disputes, legal requests, security incidents, and account deletion always go to a person.
*   A customer who explicitly asks for a person is handed off.
*   A customer who contacts us again within 7 days about the same issue while upset is handed off.
*   Assistant answers with a groundedness score below 0.70 after one revision are handed off.

Human agents are the only authorized personnel to process refunds, issue credits, or resolve billing disputes. Automated systems cannot grant these exceptions or final resolutions.
