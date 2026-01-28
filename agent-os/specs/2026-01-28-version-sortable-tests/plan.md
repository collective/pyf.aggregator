# Plan: Integration Tests for version_sortable Schema

## Summary

Add integration tests to verify that indexed packages have correctly formatted `version_sortable` values (zero-padded) and sort correctly in Typesense.

**Test Versions**: 1.0.3, 12.5.9, 99.0.99, 2.1.2, 2.1.3, 2.1.5

**Expected Sort Order** (ascending):
1. 1.0.3 → `0001.0000.0003.0002.0000`
2. 2.1.2 → `0002.0001.0002.0002.0000`
3. 2.1.3 → `0002.0001.0003.0002.0000`
4. 2.1.5 → `0002.0001.0005.0002.0000`
5. 12.5.9 → `0012.0005.0009.0002.0000`
6. 99.0.99 → `0099.0000.0099.0002.0000`

## Implementation Tasks

### Task 1: Save Spec Documentation

Create `agent-os/specs/2026-01-28-version-sortable-tests/` with:
- `plan.md` - This plan
- `shape.md` - Shaping notes

### Task 2: Create Test File

Create `tests/test_version_sortable_integration.py` with:

**Fixtures:**
- `typesense_client` - Real Typesense client connection
- `test_collection` - Temporary collection with unique timestamp name, auto-cleanup
- `create_test_package` - Factory for minimal test package data
- `check_typesense_available` - Skip tests if Typesense unavailable

**Test Classes:**

1. `TestVersionSortableFormat` - Unit tests for zero-padded format generation
   - `test_version_sortable_format` - Parametrized test for each version
   - `test_all_segments_are_four_digits` - Verify 5 segments, each 4 digits

2. `TestVersionSortableIndexing` - Integration tests for indexing
   - `test_documents_indexed_with_correct_version_sortable` - Verify indexed values

3. `TestVersionSortableSortOrder` - Integration tests for sorting
   - `test_sort_by_version_sortable_ascending` - Verify ascending order
   - `test_sort_by_version_sortable_descending` - Verify descending order

4. `TestVersionSortablePreRelease` - Pre-release version sorting
   - `test_prerelease_sort_order` - alpha < beta < stable (2.0.0a1, 2.0.0b1, 2.0.0)

### Task 3: Add Integration Test Marker

Add `integration` marker to `conftest.py` for selective test execution.

## Files Modified

| File | Changes |
|------|---------|
| `tests/test_version_sortable_integration.py` | New file - integration tests |
| `tests/conftest.py` | Add `integration` marker |
| `agent-os/specs/2026-01-28-version-sortable-tests/` | New spec folder |

## Technical Notes

- Collection schema includes only fields needed for version testing
- Collection name format: `test_version_sortable_{timestamp_ms}`
- Cleanup via pytest fixture teardown (try/except for ObjectNotFound)
- Current regex captures single digit for bugfix - `99.0.99` becomes bugfix=9

## Verification

```bash
# Ensure Typesense is running
docker-compose up -d

# Run integration tests
uv run pytest tests/test_version_sortable_integration.py -v -m integration

# Run all tests
uv run pytest -v
```

## Applicable Standards

- **testing/test-writing.md**: TDD approach, mock external dependencies, fast execution
- **global/validation.md**: Validate data types and formats systematically
