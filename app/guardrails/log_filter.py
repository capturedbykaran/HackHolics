"""Redact PII/secrets from every log record. Owner: A.

A logging.Filter on the root logger only sees records logged directly on it, so install_log_filter()
also adds the filter to every root handler and wraps the LogRecord factory (covers handlers added later,
for example uvicorn's, and every logger in the process).
"""
import logging
import traceback

from app.guardrails.input_guard import redact_text

_INSTALLED = False


def _scrub(record: logging.LogRecord) -> None:
    try:
        record.msg = redact_text(record.getMessage())[0]
        record.args = ()
        if record.exc_info and not record.exc_text:
            tb = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = redact_text(tb)[0].rstrip()
    except Exception:  # noqa: BLE001 - logging must never raise
        pass


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        _scrub(record)
        return True


def install_log_filter() -> None:
    """Idempotent. Call once at startup (app/__init__.py does)."""
    global _INSTALLED
    root = logging.getLogger()
    flt = RedactingFilter()
    root.addFilter(flt)
    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(flt)
    if _INSTALLED:
        return
    _INSTALLED = True
    old_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        _scrub(record)
        return record

    logging.setLogRecordFactory(factory)
