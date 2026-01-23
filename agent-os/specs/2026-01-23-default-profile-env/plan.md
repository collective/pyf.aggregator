# Plan: Allow Setting Default Profile in .env

## Summary

Add `DEFAULT_PROFILE` environment variable support so users can set a default aggregation profile (e.g., "plone", "django", "flask") without specifying `-p` on every CLI invocation.

**Behavior:**
- CLI `-p` argument takes precedence over `DEFAULT_PROFILE`
- If neither is set, current default behavior (Plone filtering) is preserved

## Implementation Tasks

1. Add dotenv support to main.py
2. Update profile handling logic to use effective_profile
3. Update --show mode profile handling
4. Update CLI help text
5. Add DEFAULT_PROFILE to .env

## Files Modified

| File | Changes |
|------|---------|
| `src/pyf/aggregator/main.py` | Add dotenv import, DEFAULT_PROFILE constant, update profile logic |
| `.env` | Add commented DEFAULT_PROFILE example |
