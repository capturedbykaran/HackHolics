from app.guardrails.log_filter import install_log_filter

install_log_filter()  # redact PII/secrets from every log record, from the first import on
