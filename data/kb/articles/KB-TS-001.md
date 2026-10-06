---
source_id: "KB-TS-001"
doc_type: "article"
title: "Error code reference"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-08-01"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Error code reference

This article is for CloudFlow customers on version 3.x and 4.x.

## Error codes

| Code | Meaning | What to do |
|---|---|---|
| CF-401 | Invalid or expired API token | Generate a new token and update the Authorization header |
| CF-403 | Token lacks the required scope | Add the missing scope to the token in Settings > API Tokens |
| CF-404 | Workflow or run not found | Check the workflow ID and that it was not archived |
| CF-409 | Run already in progress for this workflow (concurrency lock) | Wait for the active run or enable parallel runs (Business+) |
| CF-422 | Invalid payload for a step | Validate the step input against the connector schema |
| CF-429 | API rate limit exceeded for your plan | Back off using the Retry-After header or upgrade the plan |
| CF-460 | Monthly workflow run quota exhausted | Wait for the next period or upgrade the plan |
| CF-500 | Internal CloudFlow error | Retry; if it persists, check status.cloudflow.example and contact support |
| CF-503 | Connector upstream unavailable (e.g. Salesforce API returned 503) | Re-authorise the connector and enable Retry on upstream errors (4.1+) |
| CF-504 | Step exceeded its timeout | Reduce step work, raise the step timeout (max 300 s) or split the workflow |
