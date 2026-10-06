---
source_id: "KB-GS-002"
doc_type: "article"
title: "Building your first workflow"
authority_level: 1
product_versions: "4.x"
last_updated: "2026-05-20"
effective_from: ""
deprecated_on: ""
supersedes: ""
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_article"
synthetic: "Y"
---
# Building your first workflow

This article guides new users of CloudFlow 4.x through the process of creating, testing, and publishing their first automated workflow. It covers the essential steps required to connect triggers with actions and outlines the standard operational limits for workflow execution.

## Steps

Follow these instructions to create and deploy a new workflow in your CloudFlow 4.x workspace:

1. Open the **Workflows** section and click **New workflow**.
2. Pick a trigger for your automation. You can select a schedule, a webhook, or an app event to initiate the process.
3. Add steps to your workflow by using the **+** button. As you build the sequence, map fields from earlier steps to ensure data flows correctly between actions.
4. Click **Test run** to verify that your workflow executes as expected. Once you are satisfied with the results, click **Publish** to make the workflow live.

## Limits

When designing workflows in CloudFlow 4.x, be aware of the following constraints to ensure reliable execution:

* A single workflow can contain up to 50 steps.
* Each step has a default timeout of 60 seconds. This value is configurable and can be increased up to a maximum of 300 seconds per step.

Understanding these limits helps you structure your automations effectively. If a workflow requires more than 50 steps, consider splitting the logic into multiple connected workflows. Similarly, if a specific action consistently times out, you may need to adjust the timeout settings within the allowed range or optimize the step's configuration to complete within the default 60-second window. Always review your step configurations before publishing to avoid unexpected failures in production.
