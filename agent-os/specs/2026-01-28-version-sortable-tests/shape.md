# Shape: version_sortable Integration Tests

## Problem Statement

The `version_sortable` field in Typesense allows for correct lexicographic sorting of semantic versions. This requires:
- Zero-padding each version component to 4 digits
- Proper handling of pre-release versions (alpha < beta < stable)
- Correct sorting when querying Typesense

We need integration tests to verify this works correctly end-to-end.

## Solution Approach

Create integration tests that:
1. Unit test the `make_version_sortable` function for format correctness
2. Index test packages with various versions into a real Typesense instance
3. Query and verify the sort order matches expectations

## Test Data

| Version | Expected version_sortable |
|---------|---------------------------|
| 1.0.3 | 0001.0000.0003.0002.0000 |
| 2.1.2 | 0002.0001.0002.0002.0000 |
| 2.1.3 | 0002.0001.0003.0002.0000 |
| 2.1.5 | 0002.0001.0005.0002.0000 |
| 12.5.9 | 0012.0005.0009.0002.0000 |
| 99.0.99 | 0099.0000.0099.0002.0000 |

Pre-release versions:
| Version | Expected version_sortable |
|---------|---------------------------|
| 2.0.0a1 | 0002.0000.0000.0000.0001 |
| 2.0.0b1 | 0002.0000.0000.0001.0001 |
| 2.0.0 | 0002.0000.0000.0002.0000 |

## Design Decisions

1. **Use real Typesense**: Integration tests need a running Typesense instance to verify actual sorting behavior
2. **Skip if unavailable**: Tests should skip gracefully if Typesense is not running
3. **Unique collection names**: Use timestamp-based names to avoid conflicts
4. **Automatic cleanup**: Fixture teardown deletes test collections
5. **Marker-based selection**: Use `@pytest.mark.integration` to run selectively

## Risks and Mitigations

- **Risk**: Typesense not available in CI → **Mitigation**: Skip with clear message
- **Risk**: Collection cleanup fails → **Mitigation**: Try/except with logging
- **Risk**: Regex captures wrong bugfix → **Mitigation**: Documented as known limitation for multi-digit bugfix versions like 99.0.99 (captures last digit only)

## Out of Scope

- Fixing the regex to capture multi-digit bugfix versions (separate task)
- Performance testing of sorting
- Testing all edge cases of version strings
