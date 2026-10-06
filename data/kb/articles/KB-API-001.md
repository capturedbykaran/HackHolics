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
provenance: "template:mock"
synthetic: "Y"
---
# API authentication with scoped tokens

This article is for CloudFlow customers on version 4.x.

## Create a token

- Go to Settings > API Tokens > New token.
- Choose scopes such as workflows:read, workflows:write, runs:read.
- The token is shown once; store it in a secret manager.

## Use the token

- Send it as Authorization: Bearer <token>.
- Missing scopes return CF-403; invalid or expired tokens return CF-401.
