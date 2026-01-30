#!/usr/bin/env bash
set -euo pipefail

# Run ruff format
echo "[stop-hook] Running ruff format"
FORMAT_OUTPUT=$(uv run --extra test ruff format . 2>&1) || true
FORMAT_EXIT=${PIPESTATUS[0]:-$?}

# Check if format made changes (ruff format exits 0 even when reformatting)
if echo "$FORMAT_OUTPUT" | grep -q "file reformatted\|files reformatted"; then
  cat << EOF
{"decision": "block", "reason": "RUFF FORMAT made changes. Files were reformatted. Retry stopping automatically.\n\nChanges:\n${FORMAT_OUTPUT}"}
EOF
  exit 0
fi

# Run ruff check --fix
echo "[stop-hook] Running ruff check --fix"
CHECK_OUTPUT=$(uv run --extra test ruff check --fix . 2>&1) && CHECK_EXIT=0 || CHECK_EXIT=$?

if [ $CHECK_EXIT -ne 0 ]; then
  cat << EOF
{"decision": "block", "reason": "RUFF CHECK FAILED after autofix. Fix remaining issues and retry stopping automatically.\n\nRemaining issues:\n${CHECK_OUTPUT}"}
EOF
  exit 0
fi

# Run ruff check
echo "[stop-hook] Running ruff check"
CHECK_OUTPUT=$(uv run --extra test ruff check . 2>&1) && CHECK_EXIT=0 || CHECK_EXIT=$?

if [ $CHECK_EXIT -ne 0 ]; then
  cat << EOF
{"decision": "block", "reason": "RUFF CHECK FAILED after autofix. Fix remaining issues and retry stopping automatically.\n\nRemaining issues:\n${CHECK_OUTPUT}"}
EOF
  exit 0
fi

# Run pytest
echo "[stop-hook] Running pytest"
TEST_OUTPUT=$(uv run pytest 2>&1) && TEST_EXIT=0 || TEST_EXIT=$?

if [ $TEST_EXIT -ne 0 ]; then
  # Extract just the failure summary (last 50 lines)
  SUMMARY=$(echo "$TEST_OUTPUT" | tail -50)
  cat << EOF
{"decision": "block", "reason": "PYTEST FAILED. Fix failing tests and retry stopping automatically.\n\nTest failures:\n${SUMMARY}"}
EOF
  exit 0
fi

echo "[stop-hook] All checks passed"
exit 0
