#!/usr/bin/env bash
set -euo pipefail

# JSON escape function to properly escape strings for JSON embedding
json_escape() {
  printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

# Run ruff format
echo "[stop-hook] Running ruff format" >&2
FORMAT_OUTPUT=$(uv run --extra test ruff format . 2>&1) || true
FORMAT_EXIT=${PIPESTATUS[0]:-$?}

# Check if format made changes (ruff format exits 0 even when reformatting)
if echo "$FORMAT_OUTPUT" | grep -q "file reformatted\|files reformatted"; then
  ESCAPED_OUTPUT=$(json_escape "$FORMAT_OUTPUT")
  cat << EOF
{"decision": "block", "reason": "RUFF FORMAT made changes. Files were reformatted. Retry stopping automatically.\n\nChanges:\n${ESCAPED_OUTPUT}"}
EOF
  exit 0
fi

# Run ruff check --fix
echo "[stop-hook] Running ruff check --fix" >&2
CHECK_OUTPUT=$(uv run --extra test ruff check --fix . 2>&1) && CHECK_EXIT=0 || CHECK_EXIT=$?

if [ $CHECK_EXIT -ne 0 ]; then
  ESCAPED_OUTPUT=$(json_escape "$CHECK_OUTPUT")
  cat << EOF
{"decision": "block", "reason": "RUFF CHECK FAILED after autofix. Fix remaining issues and retry stopping automatically.\n\nRemaining issues:\n${ESCAPED_OUTPUT}"}
EOF
  exit 0
fi

# Run ruff check
echo "[stop-hook] Running ruff check" >&2
CHECK_OUTPUT=$(uv run --extra test ruff check . 2>&1) && CHECK_EXIT=0 || CHECK_EXIT=$?

if [ $CHECK_EXIT -ne 0 ]; then
  ESCAPED_OUTPUT=$(json_escape "$CHECK_OUTPUT")
  cat << EOF
{"decision": "block", "reason": "RUFF CHECK FAILED after autofix. Fix remaining issues and retry stopping automatically.\n\nRemaining issues:\n${ESCAPED_OUTPUT}"}
EOF
  exit 0
fi

# Run pytest
echo "[stop-hook] Running pytest" >&2
TEST_OUTPUT=$(uv run pytest 2>&1) && TEST_EXIT=0 || TEST_EXIT=$?

if [ $TEST_EXIT -ne 0 ]; then
  # Extract just the failure summary (last 50 lines)
  SUMMARY=$(echo "$TEST_OUTPUT" | tail -50)
  ESCAPED_SUMMARY=$(json_escape "$SUMMARY")
  cat << EOF
{"decision": "block", "reason": "PYTEST FAILED. Fix failing tests and retry stopping automatically.\n\nTest failures:\n${ESCAPED_SUMMARY}"}
EOF
  exit 0
fi

echo "[stop-hook] All checks passed" >&2
exit 0
