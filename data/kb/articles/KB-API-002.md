---
source_id: "KB-API-002"
doc_type: "article"
title: "Legacy API keys (3.x)"
authority_level: 1
product_versions: "3.x"
last_updated: "2026-08-20"
effective_from: ""
deprecated_on: "2026-12-01"
supersedes: ""
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_article"
synthetic: "Y"
---
# Legacy API keys (3.x)

This article is for administrators and developers currently using CloudFlow version 3.x. It explains how to use the existing API key and outlines the upcoming deprecation schedule.

## Using legacy keys

In CloudFlow 3.x, API authentication relies on a single, account-wide key. This key is not tied to specific users or projects; it grants access to the entire account.

To use the legacy key in your integration, include it in the HTTP request header. The header name must be exactly `X-CF-Key`.

Key characteristics:
*   **Scope:** The key has full access to all resources within the account.
*   **Limitations:** You cannot restrict permissions or scope the key to specific endpoints or data sets.
*   **Management:** There is only one key per account. If you need to rotate the key, you must update all integrations simultaneously.

Because the key cannot be scoped, treat it with high security. Store it in a secure environment variable or secret manager, never in client-side code or public repositories.

## Deprecation

Legacy API keys are scheduled for removal. They will stop working on 2026-12-01. For detailed release notes, see RN-DEP-001.

To avoid service disruption, you must migrate your integrations before this date. The recommended path is to upgrade your CloudFlow instance to version 4.x. Version 4.x introduces scoped tokens, which allow you to create multiple keys with specific permission sets.

Migration steps:
1.  Upgrade your CloudFlow instance to version 4.x.
2.  Generate new scoped tokens with the specific permissions required by your integration.
3.  Update your integration code to use the new token format and headers.
4.  Test the integration in a staging environment.
5.  Deploy the changes to production.
6.  Revoke the legacy API key once all integrations are confirmed working.

Do not wait until the last minute to migrate. The deprecation date is firm, and no extensions will be granted. If you have questions about the migration process, contact support.
