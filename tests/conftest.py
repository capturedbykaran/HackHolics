"""Shared fixtures: temp DB, MOCK_LLM=true.

Owner: B
"""

import os

os.environ.setdefault("MOCK_LLM", "true")
