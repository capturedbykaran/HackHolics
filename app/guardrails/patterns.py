"""Every regex and phrase list used by the guardrails, in ONE place. Owner: A.

Rule for all guardrails: they can only make a decision stricter, never more lenient.
Patterns are deliberately conservative: a false positive costs a revision or an escalation,
a false negative can leak data.
"""
import re

I = re.I

# =============================================================== PII / secrets (redaction)
# Email address.
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# International phone: leading + then 10-18 digits/spaces/brackets/hyphens, e.g. +91 98765 43210.
PHONE_INTL = re.compile(r"(?<![\w-])\+\d[\d ()-]{8,16}\d")
# Indian mobile: 10 digits starting 6-9 (not inside a longer number or an id like INV-2026...).
PHONE_IN = re.compile(r"(?<![\w-])[6-9]\d{9}(?![\w-])")
# US style: (555) 123-4567 / 555-123-4567.
PHONE_US = re.compile(r"(?<![\w-])\(?\d{3}\)?[ -]\d{3}[ -]\d{4}(?![\w-])")
# 13-19 digits, optional space/hyphen separators. Only redacted when the Luhn check passes.
CARD_CANDIDATE = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])")
# Aadhaar: 12 digits as 4-4-4. The look-arounds stop it matching inside a 16-digit card number.
AADHAAR = re.compile(r"(?<![\w-])(?<!\d[ -])\d{4}[ -]\d{4}[ -]\d{4}(?![\w-])(?![ -]\d)")
# PAN: five letters, four digits, one letter (ABCDE1234F).
PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
# Key-like prefixes: sk-/pk-/rk-... and cf_live_/cf_test_...
API_KEY_PREFIX = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{10,}|\bcf_(?:live|test)_[A-Za-z0-9]{6,}")
# "Authorization: Bearer <token>"; group 1 is kept.
BEARER = re.compile(r"\b(Bearer\s+)[A-Za-z0-9_\-.=+/]{8,}", I)
# token=<16+ chars>; group 1 (the label) is kept.
KV_TOKEN = re.compile(r"\b((?:(?:access|auth|refresh)[_-]?)?token\s*[=:]\s*[\"']?)[A-Za-z0-9_\-.=+/]{16,}", I)
# key= / api_key= / secret= <16+ chars>; group 1 is kept.
KV_KEY = re.compile(r"\b((?:api[_-]?key|secret(?:[_-]?key)?|key)\s*[=:]\s*[\"']?)[A-Za-z0-9_\-.=+/]{16,}", I)
# "password: xxx" / "password is xxx" (already-redacted values are skipped so redaction is idempotent).
PASSWORD = re.compile(r"\b((?:password|passwd|pwd)\s*(?:[:=]|\bis\b)\s*[\"']?)(?!\[PASSWORD\])[^\s\"',;]+", I)

# =============================================================== ids we must NOT redact
ACCOUNT_ID = re.compile(r"\bA\d{4}\b")  # A1234 (invoice ids INV-..., CF-503 and 4.3 are never touched)

# =============================================================== secrets in OUTPUT
# Reset / verification / magic links and any URL carrying a token.
RESET_LINK = re.compile(r"https?://\S*(?:reset|verify|verification|magic|token|confirm)\S*", I)
# "password: hunter2", "token = abcdef...", "api key is xyz..." (value not already redacted).
SECRET_ASSIGN = re.compile(
    r"\b(?:password|passwd|token|api[ _-]?key|secret)\s*(?:[:=]|\bis\b)\s*(?!\[)[^\s\"',;]{6,}", I)
URL = re.compile(r"https?://[^\s<>\"')\]]+", I)

# =============================================================== secret / reset requests (R9)
_SECRET_NOUN = (r"(?:password|passwd|api[ _-]?keys?|secret[ _-]?keys?|secrets?|access[ _-]?tokens?|"
                r"auth(?:entication)?[ _-]?tokens?|tokens?|credentials?|"
                r"(?:password[ _-]?reset|reset|verification|magic|login)\s+links?)")
_DET = r"(?:(?:my|our|the|your)\s+)?(?:(?:current|full|actual|new|old|account|admin)\s+)*"
# "show/send/give me the API key", "tell me my password" - the secret is the direct object.
SECRET_REQUEST = re.compile(
    r"\b(?:show|send|give|tell|display|share|reveal|print|paste|email|dm|text)\s+(?:me\s+|us\s+)?"
    + _DET + _SECRET_NOUN + r"\b"
    r"|\bwhat(?:'s|\s+is)\s+my\s+" + _SECRET_NOUN + r"\b"
    r"|\b(?:i\s+(?:need|want)|can\s+(?:i|you)\s+(?:get|have|see))\s+(?:my|the)\s+" + _SECRET_NOUN + r"\b", I)
# Genuine password-reset intent: handled by the send_password_reset tool, which never returns the link.
RESET_REQUEST = re.compile(
    r"\b(?:reset|forgot|forgotten|recover|change|lost)\b[^.?!\n]{0,25}\bpassword\b"
    r"|\bpassword\s+reset\b|\b(?:reset|verification|magic|login)\s+link\b", I)

# =============================================================== prompt injection (R10)
# Name -> regex. Used on customer messages (flag + neutralise, never auto-refuse).
INJECTION_PHRASES: dict[str, re.Pattern] = {
    "ignore_instructions": re.compile(
        r"\b(?:ignore|disregard|forget|override)\b[^.?!\n]{0,30}\b"
        r"(?:instructions?|rules?|prompts?|guidelines|policies|directions)\b", I),
    "role_override": re.compile(r"\byou\s+are\s+now\b", I),
    "act_as": re.compile(r"\bact\s+as\b", I),
    "developer_mode": re.compile(r"\b(?:developer|jailbreak|god)\s+mode\b", I),
    "system_prompt": re.compile(r"\bsystem\s+prompt\b", I),
    "reveal_prompt": re.compile(
        r"\b(?:reveal|show|print|repeat|display|output)\b[^.?!\n]{0,20}\b"
        r"(?:your|the)\s+(?:prompt|instructions|rules)\b", I),
    "auto_approve": re.compile(
        r"\bapprove\b[^.?!\n]{0,30}\b(?:refund|credit|request)\b[^.?!\n]{0,30}\bautomatic(?:ally)?\b"
        r"|\bautomatically\s+approve\b", I),
    "role_tags": re.compile(
        r"</?\s*(?:system|assistant|user|human|customer_message|conversation_history|sources|"
        r"tool_results|draft|instructions?)\s*>|\[/?INST\]|<\|[a-z_]+\|>", I),
    "instruction_heading": re.compile(r"^\s*#{2,}\s*(?:instruction|system|prompt)", I | re.M),
}
# Stricter subset for retrieved documents (an article may legitimately say "act as" or "system prompt").
CHUNK_INJECTION_NAMES = ("ignore_instructions", "role_override", "developer_mode", "reveal_prompt",
                         "auto_approve", "role_tags", "instruction_heading", "assistant_directive")
INJECTION_PHRASES["assistant_directive"] = re.compile(
    r"\b(?:ai|assistant|chatbot|bot|llm)\b[^.?!\n]{0,20}\b(?:must|should|shall|will)\b[^.?!\n]{0,40}\b"
    r"(?:tell|say|send|email|reveal|ask)\b|\bwhen\s+(?:answering|replying|responding)\b", I)
# Tag-like text that could close or open one of our prompt delimiters.
TAG_LIKE = re.compile(r"<(/?\s*[A-Za-z_!][^<>]*)>")
TAG_OPEN_LIKE = re.compile(r"<(?=/?\s*[A-Za-z_!])")
HEADING_INSTRUCTION = re.compile(r"^(\s*)#{2,}(\s*(?:instruction|system|prompt))", I | re.M)

# =============================================================== abusive language
ABUSIVE = re.compile(
    r"\b(?:idiots?|stupid|useless|morons?|dumb|crap|damn|bullshit|bastards?|assholes?|wtf|stfu|"
    r"shut\s+up|piece\s+of\s+(?:shit|crap|junk))\b|\bf+\W?u+\W?c+\W?k+\w*|\bsh[i1]t\w*", I)

# =============================================================== unsafe model output (layer 3)
# Promises/confirmations of money or discounts that only a human may approve.
REFUND_PROMISE = re.compile(
    r"\bi(?:['’]ve|\s+have)\s+(?:just\s+)?(?:refunded|issued|credited|processed|approved|waived)\b"
    r"|\bwe(?:['’]ll|\s+will)\s+(?:refund|credit|waive)\b"
    r"|\b(?:your\s+)?refund\s+(?:has\s+been|is|will\s+be)\s+(?:approved|processed|issued|guaranteed)\b"
    r"|\byou(?:['’]ll|\s+will)\s+(?:receive|get)\s+(?:a\s+|an\s+)?(?:full\s+)?(?:refund|credit|discount)\b"
    r"|\bi(?:['’]ll|\s+will)\s+(?:refund|credit)\b"
    r"|\b(?:i|we)(?:['’]ve|\s+have|['’]ll|\s+will)\s+(?:apply|applied|give|gave|grant|granted)\b[^.?!\n]{0,20}\bdiscount\b"
    r"|\b(?:full|guaranteed)\s+refund\b", I)
# Claims that the system changed something: it never executes account actions.
ACCOUNT_ACTION_CLAIM = re.compile(
    r"\bi(?:['’]ve|\s+have)\s+(?:just\s+)?(?:changed|cancell?ed|upgraded|downgraded|deleted|reset|updated|"
    r"closed|suspended|reactivated|removed|transferred|disabled|enabled)\b"
    r"|\bi(?:['’]ll|\s+will)\s+(?:upgrade|downgrade|cancel|delete|reset|change|close|suspend)\b"
    r"|\byour\s+(?:plan|account|subscription|password|seats?)\s+(?:has\s+been|was|is\s+now)\s+"
    r"(?:changed|cancell?ed|upgraded|downgraded|deleted|reset|updated|closed|suspended)\b", I)
# Fragments of our own system prompts (case-sensitive on purpose: "RULES", "Return JSON ...").
PROMPT_LEAK = re.compile(
    r"\bRULES\b|Return JSON with|Return ONLY one JSON|You are a strict reviewer|"
    r"You write support replies for CloudFlow|You classify customer support messages|"
    r"SOURCES and TOOL RESULTS|</?(?:customer_message|conversation_history|sources|tool_results|draft)>")
# Chain-of-thought markers.
REASONING_LEAK = re.compile(
    r"</?think>|\blet me think\b|\bstep[- ]by[- ]step reasoning\s*:|\bchain[- ]of[- ]thought\b|"
    r"\bmy reasoning\s*:|\bthinking\s*:", I)
THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", I | re.S)
THINK_UNCLOSED = re.compile(r"<think>.*\Z", I | re.S)
THINK_STRAY = re.compile(r"</?think>", I)

# =============================================================== limits
MAX_MESSAGE_CHARS = 4000
MAX_ANSWER_CHARS = 1500
