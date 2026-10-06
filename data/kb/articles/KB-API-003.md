---
source_id: "KB-API-003"
doc_type: "article"
title: "Rate limits and handling 429 errors"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-07-01"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Rate limits and handling 429 errors

This article is for CloudFlow customers on version 3.x and 4.x.

## Limits per plan

- Free 60, Pro 300, Business 1000, Enterprise 5000 requests per minute.

## Response headers

- X-RateLimit-Limit, X-RateLimit-Remaining and Retry-After are returned on every response.

## Handling CF-429

- Wait for the number of seconds in Retry-After before retrying.
- Use exponential backoff with jitter.
- Batch requests with the /v2/runs:batch endpoint (4.x).
