---
source_id: "KB-TS-002"
doc_type: "article"
title: "Fixing CF-503 errors in Salesforce steps"
authority_level: 1
product_versions: "4.1+"
last_updated: "2026-02-12"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Fixing CF-503 errors in Salesforce steps

This article is for CloudFlow customers on version 4.1+.

## Cause

- CF-503 means Salesforce returned 503 Service Unavailable to CloudFlow.

## Fix

- Re-authorise the Salesforce connection under Connections.
- Turn on Retry on upstream errors in the Salesforce step settings (4.1+).
- Check check_platform_status for a connectors incident.

## Do not

- Do not add a Delay step before the Salesforce step; it no longer helps and can cause CF-504 timeouts.
