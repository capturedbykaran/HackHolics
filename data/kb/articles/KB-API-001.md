---
source_id: "KB-API-001"
doc_type: "article"
title: "API authentication with scoped tokens"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-08-20"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_article"
synthetic: "Y"
---
# API authentication with scoped tokens

This article explains how to generate and use scoped API tokens for CloudFlow 4.x. It is intended for developers and system administrators who need to integrate third-party tools or scripts with the CloudFlow API.

## Create a token

To generate a new API token, follow these steps:

1. Go to Settings > API Tokens > New token.
2. Choose scopes such as workflows:read, workflows:write, runs:read.
3. Copy the generated token immediately.

The token is shown once; store it in a secret manager. Do not write the token to plain text files or commit it to version control systems. Once you leave the creation screen, you cannot view the token again. If you lose the token, you must create a new one and update your integrations.

## Use the token

To authenticate your API requests, include the token in the HTTP header of every request. Send it as Authorization: Bearer <token>. Replace `<token>` with your actual secret string.

For example, a valid request header looks like this:

```
Authorization: Bearer cf_live_abc123xyz
```

If your request fails, check the error code returned by the API to determine the cause:

- Missing scopes return CF-403. This indicates that the token is valid but lacks the specific permission required for the requested action.
- Invalid or expired tokens return CF-401. This indicates that the token string is incorrect, has been revoked, or is no longer active.

Always verify that the scopes assigned to your token match the operations your application performs. Requesting write access when only read access is available will result in a CF-403 error. Regularly rotate your tokens and update your secret manager to maintain security.
