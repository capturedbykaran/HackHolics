---
source_id: "KB-CF-DEMO-001"
doc_type: "article"
title: "Configuring Slack Notification Webhooks in CloudFlow"
authority_level: 1
product_versions: "4.x;3.8+"
last_updated: "2026-10-06"
effective_from: "2026-01-01"
deprecated_on: ""
supersedes: ""
provenance: "internal:dev"
synthetic: "N"
---
# Configuring Slack Notification Webhooks in CloudFlow

This guide explains how to set up real-time alerting from CloudFlow workflow runs to your Slack channels using webhook integrations.

## Overview

Slack integrations allow CloudFlow to dispatch alert payloads whenever a workflow run succeeds, fails, or reaches a retry threshold. This feature is supported in CloudFlow version 3.8 and higher, including all 4.x releases.

## Setup Instructions

To configure a Slack incoming webhook:

1. Navigate to **Settings > Integrations > Slack**.
2. Click **Add Webhook Connection**.
3. Enter your Slack Incoming Webhook URL in the format `https://hooks.slack.com/services/...`.
4. Select the event triggers you wish to forward:
   - `workflow.failed` (Default)
   - `workflow.completed`
   - `rate_limit.warning`
5. Click **Save and Test Connection** to dispatch a ping event.

## Supported Notification Events & Rate Limits

The following table lists notification payload limits across different CloudFlow subscription plans:

| Plan Tier | Max Webhooks / Min | Retry Backoff | Custom JSON Templates |
| :--- | :--- | :--- | :--- |
| **Free** | 10 calls/min | 5s fixed | No |
| **Pro** | 60 calls/min | Exponential (up to 30s) | Yes |
| **Business** | 300 calls/min | Exponential (up to 60s) | Yes |
| **Enterprise** | Unlimited | Dedicated retry queue | Yes |

## Troubleshooting Errors

If your Slack webhook fails with error code `CF-SLACK-403`:
- Verify that your webhook URL has not been revoked in your Slack App settings.
- Ensure the target channel still exists and the CloudFlow Bot has permission to post to private channels.
- In CloudFlow 4.3+, check that your outbound firewall allows traffic to `hooks.slack.com` on port 443.

