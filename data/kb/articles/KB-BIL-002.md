---
source_id: "KB-BIL-002"
doc_type: "article"
title: "Updating your payment method and failed payments"
authority_level: 1
product_versions: "3.x;4.x"
last_updated: "2026-06-11"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_article"
synthetic: "Y"
---
# Updating your payment method and failed payments

This article explains how to update your billing details and what happens if a payment fails. It applies to CloudFlow versions 3.x and 4.x.

## Update your card

Keep your payment information current to avoid service interruptions. You can update your card details at any time through your account settings.

1. Go to Settings > Billing > Payment method.
2. Select the option to add or update a card.
3. Enter your new card details and confirm the change.

For security, CloudFlow stores only the last four digits of your card. We do not store the full card number, expiration date, or CVV code on our servers.

## Failed payments

If we cannot process a charge, your account status changes. Understanding the timeline helps you take action before your service is affected.

- After a failed payment the account becomes past_due.
- We retry the charge after 3 and 7 days.
- Accounts still unpaid after 14 days are suspended; workflows stop running but data is kept for 30 days.

If your account becomes past_due, you should update your payment method immediately. The system will automatically attempt to charge the new card during the next retry cycle. If you do not update your card, the account will remain in the past_due state until the 14-day threshold is reached.

Once an account is suspended, all active workflows stop running. This means no new tasks are triggered and existing automations pause. However, your data is not deleted. We keep your data for 30 days after suspension. If you resolve the payment issue within this 30-day window, your workflows will resume, and your data remains intact. If you do not pay within 30 days, your data may be permanently deleted.

To prevent suspension, ensure your card has sufficient funds and is not expired. If you believe a payment failed in error, contact support with your account ID and the date of the failed transaction. We can investigate the specific error code and assist you in resolving the billing issue.
