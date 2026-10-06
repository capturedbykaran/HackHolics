---
source_id: "KB-API-004"
doc_type: "article"
title: "Verifying webhook signatures (4.x)"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-03-30"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Verifying webhook signatures (4.x)

This article is for CloudFlow customers on version 4.x.

## How signing works

- 4.x signs every webhook with HMAC-SHA256 in the X-CF-Signature header.
- The signing secret is shown under the workflow's Webhook settings.

## Verify

- Compute HMAC-SHA256 of the raw request body with the secret.
- Compare using a constant-time comparison.
- Reject requests older than 5 minutes using X-CF-Timestamp.
