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
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_article"
synthetic: "Y"
---
# Product versions: 3.x and 4.x

This article helps you identify your current CloudFlow version, understand the key technical differences between the 3.x and 4.x releases, and learn how to upgrade if you are currently on the older version.

## Which version am I on?

You can determine your active version by navigating to **Settings > About** in your CloudFlow dashboard. The specific version number is displayed in this section.

*   **3.x (latest 3.8)**: This version is in maintenance mode. It receives security fixes only and no new feature development.
*   **4.x (latest 4.3)**: This is the current version of the platform, receiving full feature support and updates.

## Main differences

The transition from 3.x to 4.x involves several important changes to security and interface layout.

*   **API Authentication**: 4.x replaces legacy API keys with scoped API tokens. This provides finer-grained control over permissions.
*   **Webhook Security**: 4.x signs webhooks with HMAC-SHA256. In contrast, 3.x uses HMAC-SHA1.
*   **Interface Changes**: In 4.2+, run history export moved to the Workflows page. Users on earlier 4.x versions or 3.x should note this location change when accessing export tools.

## Upgrading

If you are on 3.x and wish to move to 4.x, you can initiate the upgrade process directly from the dashboard.

1.  Navigate to **Settings > About > Upgrade to 4.x**.
2.  Follow the on-screen prompts to confirm the upgrade.

The upgrade keeps all workflows intact. Additionally, legacy API keys keep working until 2026-12-01, allowing you time to migrate your integrations to scoped API tokens without immediate service disruption.
