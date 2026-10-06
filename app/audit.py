"""Audit trail helpers.

Owner: D
"""

def new_trace() -> str: raise NotImplementedError
def write_audit(trace_id, record): raise NotImplementedError
def append_conversation(conversation_id, turn): raise NotImplementedError
