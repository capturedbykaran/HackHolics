---
source_id: "KB-GS-005"
doc_type: "article"
title: "Product versions: 3.x and 4.x"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-08-28"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "template:mock"
synthetic: "Y"
---
# Product versions: 3.x and 4.x

This article is for CloudFlow customers on version 3.x and 4.x.

## Which version am I on?

- Your version is shown under Settings > About.
- 3.x (latest 3.8) is in maintenance and receives security fixes only.
- 4.x (latest 4.3) is the current version.

## Main differences

- 4.x replaces legacy API keys with scoped API tokens.
- 4.x signs webhooks with HMAC-SHA256; 3.x uses HMAC-SHA1.
- In 4.2+ run history export moved to the Workflows page.

## Upgrading

- Owners can upgrade from Settings > About > Upgrade to 4.x.
- The upgrade keeps all workflows; legacy API keys keep working until 2026-12-01.
