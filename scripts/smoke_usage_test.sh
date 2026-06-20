#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8000}"
curl -s -X POST "$BASE_URL/gateway/message" \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste smoke","user_id":"smoke-user","session_id":"smoke-session","message_id":"smoke-1"}}' | python -m json.tool
curl -s "$BASE_URL/debug/usage" | python -m json.tool
