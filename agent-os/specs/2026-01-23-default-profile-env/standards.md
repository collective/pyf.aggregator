# Conventions Standard

## Environment Variable Naming

- Use SCREAMING_SNAKE_CASE for environment variables
- Prefix with app name not required (already in pyf.aggregator namespace)

## Logging

- Log the source of profile selection: "(from CLI)" or "(from DEFAULT_PROFILE)"
- Use logger.info for configuration decisions

## dotenv Usage

- Load dotenv at module level, before argument parsing
- Use `os.getenv()` with no default to distinguish unset from empty
