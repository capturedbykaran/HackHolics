#!/usr/bin/env bash
# Owner: D
BASE=${BASE:-http://localhost:8000}

curl -s "$BASE/health"
