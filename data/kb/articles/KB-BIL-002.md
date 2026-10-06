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
provenance: "template:mock"
synthetic: "Y"
---
# Updating your payment method and failed payments

This article is for CloudFlow customers on version 3.x and 4.x.

## Update your card

- Go to Settings > Billing > Payment method.
- CloudFlow stores only the last four digits of your card.

## Failed payments

- After a failed payment the account becomes past_due.
- We retry the charge after 3 and 7 days.
- Accounts still unpaid after 14 days are suspended; workflows stop running but data is kept for 30 days.
