---
source_id: "KB-API-005"
doc_type: "article"
title: "Connecting Salesforce"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-02-12"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Connecting Salesforce

This article is for CloudFlow customers on version 4.x.

## Connect

- Go to Connections > Add > Salesforce and sign in with OAuth.
- The connected user needs API Enabled permission in Salesforce.

## Retries

- From 4.1, Salesforce steps have Retry on upstream errors, which retries 503 responses up to 3 times with backoff.
