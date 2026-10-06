---
source_id: "KB-TS-004"
doc_type: "article"
title: "Fixing CF-504 step timeouts"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-05-14"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Fixing CF-504 step timeouts

This article is for CloudFlow customers on version 3.x and 4.x.

## Fix

- Raise the step timeout up to 300 seconds.
- Split large loops into a separate workflow.
- Avoid long Delay steps inside loops.
