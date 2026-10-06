---
source_id: "KB-API-004-3X"
doc_type: "article"
title: "Verifying webhook signatures (3.x)"
authority_level: 1
product_versions: "3.x"
last_updated: "2025-09-14"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Verifying webhook signatures (3.x)

This article is for CloudFlow customers on version 3.x.

## How signing works

- 3.x signs webhooks with HMAC-SHA1 in the X-CF-Signature header.
- No timestamp header is sent in 3.x.
