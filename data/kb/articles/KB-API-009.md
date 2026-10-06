---
source_id: "KB-API-009"
doc_type: "article"
title: "REST API reference (v2)"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-07-15"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# REST API reference (v2)

This article is for CloudFlow customers on version 4.x.

## Base URL and versioning

- All endpoints live under https://api.cloudflow.example/v2.
- Breaking changes ship only in a new major path such as /v3.
- Responses are JSON; timestamps are ISO 8601 in UTC.

## Endpoints

| Method | Path | Scope | Purpose |
|---|---|---|---|
| GET | /v2/workflows | workflows:read | List workflows |
| POST | /v2/workflows | workflows:write | Create a workflow |
| GET | /v2/workflows/{id}/runs | runs:read | List runs, newest first, cursor pagination |
| POST | /v2/workflows/{id}/runs | runs:write | Start a run |
| POST | /v2/runs:batch | runs:write | Start up to 100 runs in one request (4.3+) |
| GET | /v2/usage | account:read | Current period usage |
| GET | /v2/tokens | tokens:read | List API tokens (values are never returned) |


## Errors

- Errors return a JSON body with code, message and request_id.
- Quote the request_id when contacting support.
- See KB-TS-001 for the full error code list.

## Idempotency

- POST requests accept an Idempotency-Key header.
- Keys are remembered for 24 hours.
- Repeating a request with the same key returns the original response instead of starting a second run.
