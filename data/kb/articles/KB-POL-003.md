---
source_id: "KB-POL-003"
doc_type: "policy"
title: "Account security and password resets"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-04-18"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_policy"
synthetic: "Y"
---
# Account security and password resets

This policy defines the security protocols for account access and incident response within CloudFlow. It applies to all users of product versions 3.x and 4.x. Compliance with these procedures is mandatory for maintaining account integrity and ensuring the security of workflow data.

## Password resets

Access to CloudFlow accounts is strictly controlled through registered credentials. The following rules govern the password reset process:

*   Reset links are only ever sent to the registered account email.
*   Reset links expire after 30 minutes.
*   Support never shares reset links or tokens in chat.

Users must verify that their registered email address is current to receive reset notifications. If a reset link is not received within the expiration window, a new request must be initiated. No alternative delivery methods are available for reset credentials.

## Compromised accounts

If an account is suspected to be compromised, specific incident response procedures must be followed immediately.

*   Report suspected compromise immediately; it is treated as a security incident.
*   Revoke all API tokens from Settings > API Tokens.

Upon reporting a suspected compromise, the account is flagged for review. Users are responsible for revoking active API tokens to prevent unauthorized access to workflow data. Failure to report a compromise promptly may result in extended data exposure. The security team handles the investigation as a formal security incident. Users should not attempt to resolve a confirmed compromise through standard support channels without first reporting the incident. All actions taken during a security incident are logged for audit purposes. This policy ensures that all users follow a consistent procedure for protecting their accounts and the broader CloudFlow platform.
