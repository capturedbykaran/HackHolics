---
source_id: "KB-API-008"
doc_type: "article"
title: "Rotating API tokens"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-08-20"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Rotating API tokens

This article is for CloudFlow customers on version 4.x.

## Rotate

- Create the new token first, deploy it, then revoke the old one.
- Tokens can have an expiry of 30, 90 or 365 days.

## If a token leaked

- Revoke it immediately in Settings > API Tokens and treat it as a security incident.
