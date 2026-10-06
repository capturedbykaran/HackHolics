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
provenance: "LLM:groq:qwen/qwen3.8-27b,prompt:kb_gen_article"
synthetic: "Y"
---
# Understanding triggers and steps

This article is for new users of CloudFlow versions 3.x and 4.x who are setting up their first workflows. It explains the two core components of any workflow: the trigger that starts the process and the steps that define the actions taken.

## Triggers

A trigger is the event that initiates a workflow. CloudFlow supports three types of triggers. You must select one trigger type for every workflow you create.

- **Schedule triggers** run on a cron expression in the workspace time zone. Use this type when you need a workflow to start at specific times or intervals.
- **Webhook triggers** give each workflow a unique URL. External systems can send data to this URL to start the workflow.
- **App-event triggers** poll the connected app every 5 minutes on Free and every 1 minute on paid plans. Use this type to react to changes in a connected application, such as a new record being created.

## Steps

Steps are the actions that occur after a trigger fires. Each step is one action in a connected app or a built-in tool. You can add multiple steps to a workflow to create a sequence of actions.

Built-in tools include Delay, Filter, Branch, Loop and Code. These tools allow you to control the flow of your workflow without needing an external application.

1. Select a trigger for your workflow.
2. Add your first step by choosing a connected app or a built-in tool.
3. Configure the inputs for the step.
4. Add additional steps as needed.
5. Save the workflow.

When you use a connected app, ensure that the app is properly authenticated in your CloudFlow account. When you use a built-in tool, configure the specific parameters required for that tool. For example, a Delay step requires a duration, while a Filter step requires a condition.

Review your workflow logic before activating it. Ensure that the order of steps matches the intended process. You can test your workflow using the preview feature to see how data moves through each step.

If a step fails, the workflow stops unless you have configured error handling. Check the logs in the workflow history to identify any issues with specific steps. Adjust the configuration or the order of steps to resolve errors.

Understanding how triggers and steps work together allows you to build reliable automations. Start with simple workflows and add complexity as you become familiar with the available tools and connected apps.
