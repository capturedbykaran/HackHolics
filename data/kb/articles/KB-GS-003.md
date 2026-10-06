---
source_id: "KB-GS-003"
doc_type: "article"
title: "Understanding triggers and steps"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-01-15"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Understanding triggers and steps

This article is for CloudFlow customers on version 3.x and 4.x.

## Triggers

- Schedule triggers run on a cron expression in the workspace time zone.
- Webhook triggers give each workflow a unique URL.
- App-event triggers poll the connected app every 5 minutes on Free and every 1 minute on paid plans.

## Steps

- Each step is one action in a connected app or a built-in tool.
- Built-in tools include Delay, Filter, Branch, Loop and Code.
