"""CloudFlow world bible: the single source of truth for every generated artifact.

Owner: C

Articles, tickets, accounts, plan_limits and policy_registry are all generated FROM
this file, so the facts in the knowledge base, the SQLite tables and the policy
registry can never disagree. Edit facts here, then re-run the generators.
"""

AS_OF_DATE = "2026-10-06"

VERSIONS = {
    "3.x": {"latest": "3.8", "status": "maintenance", "released": "2024-03-01"},
    "4.x": {"latest": "4.3", "status": "current", "released": "2025-11-10"},
}

# ---- Plans (mirrored into SQLite plan_limits and article KB-BIL-001) --------
PLANS = {
    "Free":       {"api_rate_limit_per_min": 60,   "monthly_workflow_runs": 1_000,     "seats": 1,   "support_tier": "community", "monthly_price": 0.0},
    "Pro":        {"api_rate_limit_per_min": 300,  "monthly_workflow_runs": 20_000,    "seats": 5,   "support_tier": "standard",  "monthly_price": 49.0},
    "Business":   {"api_rate_limit_per_min": 1000, "monthly_workflow_runs": 100_000,   "seats": 25,  "support_tier": "priority",  "monthly_price": 199.0},
    "Enterprise": {"api_rate_limit_per_min": 5000, "monthly_workflow_runs": 1_000_000, "seats": 250, "support_tier": "priority",  "monthly_price": 999.0},
}

# ---- Error codes (article KB-TS-001 renders this as a table) -----------------
ERROR_CODES = [
    ("CF-401", "Invalid or expired API token", "Generate a new token and update the Authorization header"),
    ("CF-403", "Token lacks the required scope", "Add the missing scope to the token in Settings > API Tokens"),
    ("CF-404", "Workflow or run not found", "Check the workflow ID and that it was not archived"),
    ("CF-409", "Run already in progress for this workflow (concurrency lock)", "Wait for the active run or enable parallel runs (Business+)"),
    ("CF-422", "Invalid payload for a step", "Validate the step input against the connector schema"),
    ("CF-429", "API rate limit exceeded for your plan", "Back off using the Retry-After header or upgrade the plan"),
    ("CF-460", "Monthly workflow run quota exhausted", "Wait for the next period or upgrade the plan"),
    ("CF-500", "Internal CloudFlow error", "Retry; if it persists, check status.cloudflow.example and contact support"),
    ("CF-503", "Connector upstream unavailable (e.g. Salesforce API returned 503)", "Re-authorise the connector and enable Retry on upstream errors (4.1+)"),
    ("CF-504", "Step exceeded its timeout", "Reduce step work, raise the step timeout (max 300 s) or split the workflow"),
]

# ---- Policy values (mirrored into policy_registry, each linked to a clause) ---
POLICIES = [
    # rule_id, description, parameter, operator, value, scope_plans, effective_from, source_id, source_section
    ("REFUND-WINDOW-01", "Refund requests must be made within 14 days of the charge", "refund_window_days", "<=", "14", "ALL", "2025-01-01", "KB-POL-001", "Refund window"),
    ("REFUND-DUP-01", "Duplicate charges are refunded in full after billing verification", "duplicate_charge_refund", "==", "full", "ALL", "2025-01-01", "KB-POL-001", "Duplicate charges"),
    ("REFUND-FREE-01", "Free plan has no charges and is not refund-eligible", "refund_eligible_plans", "in", "Pro,Business,Enterprise", "ALL", "2025-01-01", "KB-POL-001", "Eligibility"),
    ("SLA-BILLING-01", "Billing handoffs answered within 1 business day", "sla_billing_hours", "<=", "24", "ALL", "2025-06-01", "KB-POL-002", "Response targets"),
    ("SLA-SECURITY-01", "Security handoffs answered within 4 hours", "sla_security_hours", "<=", "4", "ALL", "2025-06-01", "KB-POL-002", "Response targets"),
    ("SLA-TECH-PRIO-01", "Technical handoffs on priority support within 8 hours", "sla_technical_hours", "<=", "8", "Business,Enterprise", "2025-06-01", "KB-POL-002", "Response targets"),
    ("SLA-TECH-STD-01", "Technical handoffs on standard support within 24 hours", "sla_technical_hours", "<=", "24", "Free,Pro", "2025-06-01", "KB-POL-002", "Response targets"),
    ("ESC-GROUND-01", "Answers below this groundedness score after one revision are escalated", "critic_min_groundedness", ">=", "0.70", "ALL", "2026-09-01", "KB-POL-002", "When we hand off to a person"),
    ("ESC-REPEAT-01", "Contacts from the same account within this many days count as repeat contact", "repeat_contact_days", "<=", "7", "ALL", "2026-09-01", "KB-POL-002", "When we hand off to a person"),
]

# ---- Article specs -----------------------------------------------------------
# Each section lists FACTS the generated prose must contain. must_include strings
# are checked verbatim by validate_kb.py; a failed check triggers regeneration.
A = "article"; P = "policy"; R = "release_note"

ARTICLES = [
    # Getting started (5)
    dict(source_id="KB-GS-001", doc_type=A, category="getting_started", title="Creating your CloudFlow account", product_versions="3.x;4.x", last_updated="2026-03-12",
         sections=[("Sign up", ["Sign up at app.cloudflow.example with a work email", "Every new account starts on the Free plan", "Email verification link expires after 24 hours"]),
                   ("Set up your workspace", ["Choose a workspace name; it appears in your workflow URLs", "New accounts are created on version 4.3"]),
                   ("Next steps", ["Build your first workflow (KB-GS-002)", "Invite your team (KB-GS-004)"])],
         must_include=["Free plan", "24 hours", "4.3"]),
    dict(source_id="KB-GS-002", doc_type=A, category="getting_started", title="Building your first workflow", product_versions="4.x", last_updated="2026-05-20",
         sections=[("Steps", ["Open Workflows and click New workflow", "Pick a trigger (schedule, webhook or app event)", "Add steps with the + button and map fields from earlier steps", "Click Test run, then Publish"]),
                   ("Limits", ["A workflow can have up to 50 steps", "Each step has a default timeout of 60 seconds, configurable up to 300 seconds"])],
         must_include=["Test run", "50 steps", "300 seconds"]),
    dict(source_id="KB-GS-003", doc_type=A, category="getting_started", title="Understanding triggers and steps", product_versions="3.x;4.x", last_updated="2026-01-15",
         sections=[("Triggers", ["Schedule triggers run on a cron expression in the workspace time zone", "Webhook triggers give each workflow a unique URL", "App-event triggers poll the connected app every 5 minutes on Free and every 1 minute on paid plans"]),
                   ("Steps", ["Each step is one action in a connected app or a built-in tool", "Built-in tools include Delay, Filter, Branch, Loop and Code"])],
         must_include=["5 minutes", "1 minute", "Webhook"]),
    dict(source_id="KB-GS-004", doc_type=A, category="getting_started", title="Inviting team members and managing seats", product_versions="3.x;4.x", last_updated="2026-04-02",
         sections=[("Invite people", ["Go to Settings > Members and click Invite", "Only Owners and Admins can invite members"]),
                   ("Seats", ["Seats per plan: Free 1, Pro 5, Business 25, Enterprise 250", "Invites beyond your seat limit stay pending until a seat frees up or you upgrade"])],
         must_include=["Settings > Members", "Pro 5", "Business 25"]),
    dict(source_id="KB-GS-005", doc_type=A, category="getting_started", title="Product versions: 3.x and 4.x", product_versions="3.x;4.x", last_updated="2026-08-28",
         sections=[("Which version am I on?", ["Your version is shown under Settings > About", "3.x (latest 3.8) is in maintenance and receives security fixes only", "4.x (latest 4.3) is the current version"]),
                   ("Main differences", ["4.x replaces legacy API keys with scoped API tokens", "4.x signs webhooks with HMAC-SHA256; 3.x uses HMAC-SHA1", "In 4.2+ run history export moved to the Workflows page"]),
                   ("Upgrading", ["Owners can upgrade from Settings > About > Upgrade to 4.x", "The upgrade keeps all workflows; legacy API keys keep working until 2026-12-01"])],
         must_include=["Settings > About", "3.8", "4.3", "2026-12-01"]),

    # Account & billing (5) + policies (3)
    dict(source_id="KB-BIL-001", doc_type=P, category="account_billing", title="Plans and limits", product_versions="3.x;4.x", last_updated="2026-07-01", authority_level=1,
         sections=[("Plan comparison", ["TABLE:PLANS"]),
                   ("What happens at a limit", ["API calls above the per-minute limit return CF-429", "Workflow runs above the monthly quota return CF-460 and runs pause until the next period", "Usage resets on the 1st of each month (UTC)"])],
         must_include=["CF-429", "CF-460", "300", "20,000"]),
    dict(source_id="KB-BIL-002", doc_type=A, category="account_billing", title="Updating your payment method and failed payments", product_versions="3.x;4.x", last_updated="2026-06-11",
         sections=[("Update your card", ["Go to Settings > Billing > Payment method", "CloudFlow stores only the last four digits of your card"]),
                   ("Failed payments", ["After a failed payment the account becomes past_due", "We retry the charge after 3 and 7 days", "Accounts still unpaid after 14 days are suspended; workflows stop running but data is kept for 30 days"])],
         must_include=["past_due", "3 and 7 days", "suspended"]),
    dict(source_id="KB-BIL-003", doc_type=A, category="account_billing", title="Duplicate charges", product_versions="3.x;4.x", last_updated="2026-08-20",
         sections=[("Why it happens", ["A duplicate charge usually comes from a retried payment that succeeded twice"]),
                   ("What we do", ["Duplicate charges are refunded in full once the billing team verifies them (KB-POL-001)", "Support cannot issue refunds directly; the request is handed to billing", "Billing responds within 1 business day"])],
         must_include=["refunded in full", "1 business day", "billing"]),
    dict(source_id="KB-BIL-004", doc_type=A, category="account_billing", title="Invoices and receipts", product_versions="3.x;4.x", last_updated="2026-02-09",
         sections=[("Download invoices", ["Go to Settings > Billing > Invoices", "Invoices are issued on the 1st of each month in USD or INR"]),
                   ("Invoice statuses", ["paid, failed or refunded", "A refunded invoice shows the refund date"])],
         must_include=["Settings > Billing > Invoices", "USD or INR"]),
    dict(source_id="KB-BIL-005", doc_type=A, category="account_billing", title="Upgrading or downgrading your plan", product_versions="3.x;4.x", last_updated="2026-05-03",
         sections=[("Upgrade", ["Upgrades take effect immediately and are prorated"]),
                   ("Downgrade", ["Downgrades take effect at the next billing period", "If you use more seats than the new plan allows, remove members first"])],
         must_include=["prorated", "next billing period"]),
    dict(source_id="KB-POL-001", doc_type=P, category="policy", title="Refund policy", product_versions="3.x;4.x", last_updated="2026-01-05", authority_level=1,
         sections=[("Eligibility", ["Refunds apply to Pro, Business and Enterprise charges", "Free plan accounts have no charges to refund"]),
                   ("Refund window", ["A refund must be requested within 14 days of the charge date", "Requests made on day 15 or later are not eligible, except duplicate charges"]),
                   ("Duplicate charges", ["Duplicate charges are refunded in full after billing verification, regardless of the window"]),
                   ("Who approves", ["All refunds and credits are approved by the billing team, never by the support assistant"])],
         must_include=["14 days", "refunded in full", "billing team"]),
    dict(source_id="KB-POL-002", doc_type=P, category="policy", title="Support escalation and response times", product_versions="3.x;4.x", last_updated="2026-09-01", authority_level=1,
         sections=[("Response targets", ["Billing: within 1 business day (24 hours)", "Security: within 4 hours", "Technical on priority support (Business, Enterprise): within 8 hours", "Technical on standard support (Free, Pro): within 24 hours"]),
                   ("When we hand off to a person", ["Refunds, credits, billing disputes, legal requests, security incidents and account deletion always go to a person", "A customer who asks for a person, or contacts us again within 7 days about the same issue while upset, is handed off", "Assistant answers with a groundedness score below 0.70 after one revision are handed off"])],
         must_include=["4 hours", "8 hours", "0.70", "7 days"]),
    dict(source_id="KB-POL-003", doc_type=P, category="policy", title="Account security and password resets", product_versions="3.x;4.x", last_updated="2026-04-18", authority_level=1,
         sections=[("Password resets", ["Reset links are only ever sent to the registered account email", "Reset links expire after 30 minutes", "Support never shares reset links or tokens in chat"]),
                   ("Compromised accounts", ["Report suspected compromise immediately; it is treated as a security incident", "Revoke all API tokens from Settings > API Tokens"])],
         must_include=["registered account email", "30 minutes", "never shares"]),

    # API & integrations (8 + version variants)
    dict(source_id="KB-API-001", doc_type=A, category="api_integrations", title="API authentication with scoped tokens", product_versions="4.x", last_updated="2026-08-20",
         sections=[("Create a token", ["Go to Settings > API Tokens > New token", "Choose scopes such as workflows:read, workflows:write, runs:read", "The token is shown once; store it in a secret manager"]),
                   ("Use the token", ["Send it as Authorization: Bearer <token>", "Missing scopes return CF-403; invalid or expired tokens return CF-401"])],
         must_include=["Authorization: Bearer", "CF-403", "CF-401", "scopes"]),
    dict(source_id="KB-API-002", doc_type=A, category="api_integrations", title="Legacy API keys (3.x)", product_versions="3.x", last_updated="2026-08-20", deprecated_on="2026-12-01",
         sections=[("Using legacy keys", ["3.x uses a single account-wide API key sent in the X-CF-Key header", "Legacy keys have full access and cannot be scoped"]),
                   ("Deprecation", ["Legacy API keys stop working on 2026-12-01 (see RN-DEP-001)", "Move to scoped tokens by upgrading to 4.x"])],
         must_include=["X-CF-Key", "2026-12-01"]),
    dict(source_id="KB-API-003", doc_type=A, category="api_integrations", title="Rate limits and handling 429 errors", product_versions="3.x;4.x", last_updated="2026-07-01",
         sections=[("Limits per plan", ["Free 60, Pro 300, Business 1000, Enterprise 5000 requests per minute"]),
                   ("Response headers", ["X-RateLimit-Limit, X-RateLimit-Remaining and Retry-After are returned on every response"]),
                   ("Handling CF-429", ["Wait for the number of seconds in Retry-After before retrying", "Use exponential backoff with jitter", "Batch requests with the /v2/runs:batch endpoint (4.x)"])],
         must_include=["Retry-After", "CF-429", "Pro 300"]),
    dict(source_id="KB-API-004", doc_type=A, category="api_integrations", title="Verifying webhook signatures (4.x)", product_versions="4.x", last_updated="2026-03-30",
         sections=[("How signing works", ["4.x signs every webhook with HMAC-SHA256 in the X-CF-Signature header", "The signing secret is shown under the workflow's Webhook settings"]),
                   ("Verify", ["Compute HMAC-SHA256 of the raw request body with the secret", "Compare using a constant-time comparison", "Reject requests older than 5 minutes using X-CF-Timestamp"])],
         must_include=["HMAC-SHA256", "X-CF-Signature", "5 minutes"]),
    dict(source_id="KB-API-004-3X", doc_type=A, category="api_integrations", title="Verifying webhook signatures (3.x)", product_versions="3.x", last_updated="2025-09-14",
         sections=[("How signing works", ["3.x signs webhooks with HMAC-SHA1 in the X-CF-Signature header", "No timestamp header is sent in 3.x"])],
         must_include=["HMAC-SHA1"]),
    dict(source_id="KB-API-005", doc_type=A, category="api_integrations", title="Connecting Salesforce", product_versions="4.x", last_updated="2026-02-12",
         sections=[("Connect", ["Go to Connections > Add > Salesforce and sign in with OAuth", "The connected user needs API Enabled permission in Salesforce"]),
                   ("Retries", ["From 4.1, Salesforce steps have Retry on upstream errors, which retries 503 responses up to 3 times with backoff"])],
         must_include=["OAuth", "API Enabled", "Retry on upstream errors"]),
    dict(source_id="KB-API-006", doc_type=A, category="api_integrations", title="Connecting Slack", product_versions="3.x;4.x", last_updated="2026-01-22",
         sections=[("Connect", ["Go to Connections > Add > Slack and approve the CloudFlow app", "Private channels require inviting the CloudFlow bot with /invite @CloudFlow"])],
         must_include=["/invite @CloudFlow"]),
    dict(source_id="KB-API-007", doc_type=A, category="api_integrations", title="Listing runs with the REST API", product_versions="4.x", last_updated="2026-06-30",
         sections=[("Endpoint", ["GET /v2/workflows/{id}/runs returns runs newest first", "Requires the runs:read scope"]),
                   ("Pagination", ["Use the cursor value from the response in the next request", "Page size defaults to 50 and can be at most 200"])],
         must_include=["/v2/workflows/{id}/runs", "runs:read", "200"]),
    dict(source_id="KB-API-008", doc_type=A, category="api_integrations", title="Rotating API tokens", product_versions="4.x", last_updated="2026-08-20",
         sections=[("Rotate", ["Create the new token first, deploy it, then revoke the old one", "Tokens can have an expiry of 30, 90 or 365 days"]),
                   ("If a token leaked", ["Revoke it immediately in Settings > API Tokens and treat it as a security incident"])],
         must_include=["revoke", "365 days"]),

    # Troubleshooting (8)
    dict(source_id="KB-TS-001", doc_type=A, category="troubleshooting", title="Error code reference", product_versions="3.x;4.x", last_updated="2026-08-01",
         sections=[("Error codes", ["TABLE:ERRORS"])],
         must_include=["CF-401", "CF-429", "CF-503", "CF-504"]),
    dict(source_id="KB-TS-002", doc_type=A, category="troubleshooting", title="Fixing CF-503 errors in Salesforce steps", product_versions="4.1+", last_updated="2026-02-12",
         sections=[("Cause", ["CF-503 means Salesforce returned 503 Service Unavailable to CloudFlow"]),
                   ("Fix", ["Re-authorise the Salesforce connection under Connections", "Turn on Retry on upstream errors in the Salesforce step settings (4.1+)", "Check check_platform_status for a connectors incident"]),
                   ("Do not", ["Do not add a Delay step before the Salesforce step; it no longer helps and can cause CF-504 timeouts"])],
         must_include=["Retry on upstream errors", "Re-authorise", "Delay step", "CF-504"]),
    dict(source_id="KB-TS-003", doc_type=A, category="troubleshooting", title="Fixing CF-401 and CF-403 errors", product_versions="4.x", last_updated="2026-08-20",
         sections=[("CF-401", ["The token is invalid, revoked or expired; create a new one"]),
                   ("CF-403", ["The token is valid but missing a scope; edit the token's scopes"])],
         must_include=["CF-401", "CF-403", "scope"]),
    dict(source_id="KB-TS-004", doc_type=A, category="troubleshooting", title="Fixing CF-504 step timeouts", product_versions="3.x;4.x", last_updated="2026-05-14",
         sections=[("Fix", ["Raise the step timeout up to 300 seconds", "Split large loops into a separate workflow", "Avoid long Delay steps inside loops"])],
         must_include=["300 seconds", "CF-504"]),
    dict(source_id="KB-TS-005", doc_type=A, category="troubleshooting", title="Workflow is not triggering", product_versions="3.x;4.x", last_updated="2026-04-09",
         sections=[("Checklist", ["Confirm the workflow is Published, not Draft", "For schedule triggers, check the workspace time zone", "Check the monthly run quota; at the quota runs pause with CF-460", "Check the account is not suspended"])],
         must_include=["Published", "CF-460", "suspended"]),
    dict(source_id="KB-TS-006", doc_type=A, category="troubleshooting", title="Webhook signature mismatch", product_versions="4.x", last_updated="2026-03-30",
         sections=[("Common causes", ["Verifying a parsed body instead of the raw body", "Using SHA1 instead of HMAC-SHA256 after upgrading to 4.x", "Using the secret from a different workflow"])],
         must_include=["raw body", "HMAC-SHA256"]),
    dict(source_id="KB-TS-007", doc_type=A, category="troubleshooting", title="CF-460: monthly run quota exhausted", product_versions="3.x;4.x", last_updated="2026-07-01",
         sections=[("What it means", ["Your account used all workflow runs for the month", "Runs pause until usage resets on the 1st (UTC) or you upgrade"])],
         must_include=["CF-460", "1st"]),
    dict(source_id="KB-TS-008", doc_type=A, category="troubleshooting", title="Login and password reset problems", product_versions="3.x;4.x", last_updated="2026-04-18",
         sections=[("Reset your password", ["Click Forgot password on the sign-in page", "The reset email goes to the registered account email and the link expires after 30 minutes", "Support can trigger a reset email but never sends links in chat"])],
         must_include=["Forgot password", "30 minutes"]),

    # Advanced features (4 + version variant)
    dict(source_id="KB-ADV-001", doc_type=A, category="advanced", title="Exporting workflow run history", product_versions="4.2+", last_updated="2026-09-10",
         sections=[("Steps", ["Open Workflows and select the workflow", "Open the Runs tab and click Export", "Choose CSV or JSON and a date range of up to 90 days"]),
                   ("Notes", ["Exports include run ID, status, start and end time and error code", "Large exports are emailed as a download link to the requester"])],
         must_include=["Runs tab", "CSV or JSON", "90 days"]),
    dict(source_id="KB-ADV-001-3X", doc_type=A, category="advanced", title="Exporting run history (3.x)", product_versions="3.x", last_updated="2025-06-02",
         sections=[("Steps", ["Go to Settings > Data > Export", "Select Run history; 3.x exports CSV only, up to 30 days"])],
         must_include=["Settings > Data > Export", "CSV only", "30 days"]),
    dict(source_id="KB-ADV-002", doc_type=A, category="advanced", title="Branching and loops", product_versions="4.x", last_updated="2026-05-27",
         sections=[("Branch", ["Branch steps route data on conditions; up to 5 branches per step"]),
                   ("Loop", ["Loop steps iterate over a list of up to 1,000 items", "Each iteration counts toward the step timeout"])],
         must_include=["5 branches", "1,000 items"]),
    dict(source_id="KB-ADV-003", doc_type=A, category="advanced", title="Environment variables and secrets", product_versions="4.x", last_updated="2026-06-03",
         sections=[("Secrets", ["Store credentials under Settings > Secrets, never in step fields", "Secrets are encrypted and masked in run logs"])],
         must_include=["Settings > Secrets", "masked"]),
    dict(source_id="KB-ADV-004", doc_type=A, category="advanced", title="Audit logs", product_versions="4.x", last_updated="2026-07-19",
         sections=[("Availability", ["Audit logs are available on the Enterprise plan only", "Logs are kept for 365 days and can be exported as JSON"])],
         must_include=["Enterprise plan only", "365 days"]),

    # Release notes (3) - one deprecation takes effect AFTER as_of_date
    dict(source_id="RN-4.1", doc_type=R, category="release_notes", title="Release notes 4.1", product_versions="4.1+", last_updated="2026-02-10", effective_from="2026-02-10", authority_level=2,
         sections=[("New", ["Retry on upstream errors for Salesforce, HubSpot and Zendesk steps", "Replaces the earlier advice to add Delay steps before connector steps"])],
         must_include=["Retry on upstream errors", "Delay steps"]),
    dict(source_id="RN-4.3", doc_type=R, category="release_notes", title="Release notes 4.3", product_versions="4.3+", last_updated="2026-07-15", effective_from="2026-07-15", authority_level=2,
         sections=[("New", ["Batch runs endpoint /v2/runs:batch", "Run history export supports JSON"])],
         must_include=["/v2/runs:batch"]),
    dict(source_id="RN-DEP-001", doc_type=R, category="release_notes", title="Deprecation: legacy API keys", product_versions="3.x;4.x", last_updated="2026-08-20", effective_from="2026-12-01", authority_level=2,
         supersedes="KB-API-002",
         sections=[("What changes", ["Legacy API keys sent in X-CF-Key stop working on 2026-12-01", "Until then they keep working; migrate to scoped tokens (KB-API-001)"])],
         must_include=["2026-12-01", "X-CF-Key"]),
]

# ---- Ticket specs (25+). outdated=True tickets contradict current docs -------
T = dict
TICKETS = [
    T(source_id="TKT-2025-0311", intent="bug", product_version="4.0", resolved_at="2025-12-15", outdated=True, contradicts="KB-TS-002",
      gist_q="Salesforce step keeps failing with CF-503", gist_r="Workaround: add a 30 second Delay step before the Salesforce step"),
    T(source_id="TKT-2025-0420", intent="how_to", product_version="4.0", resolved_at="2025-12-02", outdated=True, contradicts="KB-ADV-001",
      gist_q="How do I export run history in 4.0?", gist_r="Go to Settings > Data > Export and download CSV"),
    T(source_id="TKT-2025-0518", intent="how_to", product_version="4.0", resolved_at="2025-12-20", outdated=True, contradicts="KB-API-001",
      gist_q="Which header do I use for API auth on a new integration?", gist_r="Use your account API key in the X-CF-Key header"),
    T(source_id="TKT-2026-0102", intent="bug", product_version="4.1", resolved_at="2026-03-04", outdated=True, contradicts="KB-API-004",
      gist_q="Webhook signature check fails after upgrade", gist_r="Verify the signature with SHA1 of the body"),
    T(source_id="TKT-2026-0140", intent="complaint", product_version="4.2", resolved_at="2026-05-11", needs_human=True,
      gist_q="Angry: charged twice this month, third email, wants a manager", gist_r="Escalated to billing; duplicate charge refunded in full after verification"),
    T(source_id="TKT-2026-0155", intent="complaint", product_version="4.3", resolved_at="2026-07-22", needs_human=True,
      gist_q="Angry: account suspended during a launch, workflows stopped", gist_r="Escalated to billing; failed payment retried and account reactivated"),
    T(source_id="TKT-2026-0171", intent="complaint", product_version="4.3", resolved_at="2026-08-30", needs_human=True,
      gist_q="Angry: says a teammate deleted workflows, demands data restore and compensation", gist_r="Escalated to technical and billing; workflows restored from 30-day retention, credit decided by billing"),
    T(source_id="TKT-2026-0201", intent="how_to", product_version="4.3", resolved_at="2026-09-12", gist_q="How do I rotate an API token without downtime?", gist_r="Create new token, deploy, revoke old one (KB-API-008)"),
    T(source_id="TKT-2026-0202", intent="account", product_version="4.3", resolved_at="2026-09-03", gist_q="Getting CF-429 on the Pro plan", gist_r="Peak was above 300 per minute; added backoff using Retry-After"),
    T(source_id="TKT-2026-0203", intent="account", product_version="4.2", resolved_at="2026-08-18", gist_q="Runs stopped with CF-460", gist_r="Monthly quota reached; customer upgraded to Business"),
    T(source_id="TKT-2026-0204", intent="bug", product_version="4.3", resolved_at="2026-09-01", gist_q="Step times out with CF-504 in a loop", gist_r="Raised step timeout to 300 seconds and split the loop"),
    T(source_id="TKT-2026-0205", intent="how_to", product_version="4.3", resolved_at="2026-08-07", gist_q="Slack step cannot post to private channel", gist_r="Invite the bot with /invite @CloudFlow"),
    T(source_id="TKT-2026-0206", intent="billing", product_version="4.1", resolved_at="2026-06-22", gist_q="Where can I download invoices?", gist_r="Settings > Billing > Invoices"),
    T(source_id="TKT-2026-0207", intent="billing", product_version="4.3", resolved_at="2026-09-19", gist_q="Card declined, account shows past_due", gist_r="Updated card; charge retried and succeeded"),
    T(source_id="TKT-2026-0208", intent="how_to", product_version="3.8", resolved_at="2026-04-15", gist_q="Export run history on 3.8", gist_r="Settings > Data > Export, CSV, up to 30 days"),
    T(source_id="TKT-2026-0209", intent="bug", product_version="4.3", resolved_at="2026-09-25", gist_q="CF-503 on Salesforce after 4.3 upgrade", gist_r="Re-authorised the connection and enabled Retry on upstream errors"),
    T(source_id="TKT-2026-0210", intent="account", product_version="4.3", resolved_at="2026-09-28", gist_q="Cannot invite a 6th member on Pro", gist_r="Pro includes 5 seats; customer upgraded"),
    T(source_id="TKT-2026-0211", intent="how_to", product_version="4.3", resolved_at="2026-07-30", gist_q="How do I paginate runs via API?", gist_r="Use cursor; page size up to 200"),
    T(source_id="TKT-2026-0212", intent="bug", product_version="4.2", resolved_at="2026-06-02", gist_q="Workflow not triggering on schedule", gist_r="Workflow was in Draft; published it"),
    T(source_id="TKT-2026-0213", intent="account", product_version="4.3", resolved_at="2026-08-25", gist_q="Forgot password and reset email not arriving", gist_r="Checked spam; reset email resent to registered address"),
    T(source_id="TKT-2026-0214", intent="how_to", product_version="4.3", resolved_at="2026-09-09", gist_q="Where do I store API credentials for steps?", gist_r="Settings > Secrets"),
    T(source_id="TKT-2026-0215", intent="billing", product_version="4.3", resolved_at="2026-09-14", gist_q="Refund request 20 days after charge", gist_r="Outside 14-day window; billing declined, explained policy"),
    T(source_id="TKT-2026-0216", intent="how_to", product_version="4.3", resolved_at="2026-09-21", gist_q="Can I see who changed a workflow?", gist_r="Audit logs on Enterprise only"),
    T(source_id="TKT-2026-0217", intent="bug", product_version="4.3", resolved_at="2026-09-30", gist_q="CF-403 when listing runs", gist_r="Token was missing runs:read scope"),
    T(source_id="TKT-2026-0218", intent="account", product_version="3.8", resolved_at="2026-09-02", gist_q="Should I upgrade from 3.8 to 4.x?", gist_r="Yes; legacy keys stop working 2026-12-01; upgrade under Settings > About"),
    T(source_id="TKT-2026-0219", intent="how_to", product_version="4.3", resolved_at="2026-10-01", gist_q="How many branches can a Branch step have?", gist_r="Up to 5"),
]
