---
source_id: "KB-TS-006"
doc_type: "article"
title: "Webhook signature mismatch"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-03-30"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Webhook signature mismatch

This article is for CloudFlow customers on version 4.x.

## Common causes

- Verifying a parsed body instead of the raw body.
- Using SHA1 instead of HMAC-SHA256 after upgrading to 4.x.
- Using the secret from a different workflow.
