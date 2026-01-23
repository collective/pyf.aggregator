# Shaping Notes: DEFAULT_PROFILE Environment Variable

## Problem

Users running pyfaggregator CLI frequently use the same profile (e.g., "plone") and must repeatedly specify `-p plone` on every invocation.

## Solution

Support a `DEFAULT_PROFILE` environment variable that provides a fallback when `-p` is not specified on the command line.

## Precedence Rules

1. CLI `-p/--profile` argument (highest priority)
2. `DEFAULT_PROFILE` environment variable
3. Default Plone filtering behavior (lowest priority)

## Edge Cases

- Invalid `DEFAULT_PROFILE` value: Show error with available profiles list
- Empty `DEFAULT_PROFILE`: Treat as unset, use default behavior
- Both CLI and env var set: CLI takes precedence (log which source is used)
