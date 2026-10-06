---
source_id: "KB-API-007"
doc_type: "article"
title: "Listing runs with the REST API"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-06-30"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Listing runs with the REST API

This article is for CloudFlow customers on version 4.x.

## Endpoint

- GET /v2/workflows/{id}/runs returns runs newest first.
- Requires the runs:read scope.

## Pagination

- Use the cursor value from the response in the next request.
- Page size defaults to 50 and can be at most 200.
