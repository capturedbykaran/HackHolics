---
source_id: "KB-BIL-001"
doc_type: "policy"
title: "Plans and limits"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-07-01"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Plans and limits

This article is for CloudFlow customers on version 3.x and 4.x.

## Plan comparison

| Plan | API requests/min | Workflow runs/month | Seats | Support | Price/month (USD) |
|---|---|---|---|---|---|
| Free | 60 | 1,000 | 1 | community | 0 |
| Pro | 300 | 20,000 | 5 | standard | 49 |
| Business | 1,000 | 100,000 | 25 | priority | 199 |
| Enterprise | 5,000 | 1,000,000 | 250 | priority | 999 |


## What happens at a limit

- API calls above the per-minute limit return CF-429.
- Workflow runs above the monthly quota return CF-460 and runs pause until the next period.
- Usage resets on the 1st of each month (UTC).
