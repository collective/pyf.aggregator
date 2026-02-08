# Plan: Unify CLI Commands into `pyfa`

## Context

The project has 6 separate CLI entry points (`pyfaggregator`, `pyfnpm`, `pyfupdater`, `pyfgithub`, `pyfdownloads`, `pyfhealth`) with duplicated profile/collection resolution logic (~20-30 lines each). This plan unifies them into a single `pyfa` command with subcommands, removes all old entry points, and extracts shared CLI utilities. Work happens in branch `pyfa-harmonization`.

## Subcommand Mapping

| Old Command | New Command | Source Module |
|---|---|---|
| `pyfaggregator` | `pyfa pypi` | `main.py` |
| `pyfnpm` | `pyfa npm` | `npm_main.py` |
| `pyfupdater` | `pyfa manage` | `typesense_util.py` |
| `pyfgithub` | `pyfa github` | `enrichers/github.py` |
| `pyfdownloads` | `pyfa downloads` | `enrichers/downloads.py` |
| `pyfhealth` | `pyfa health` | `enrichers/health_calculator.py` |

## Implementation Steps

### Step 1: Create branch `pyfa-harmonization`

### Step 2: Create `src/pyf/aggregator/cli_utils.py` (NEW)

Extract shared utilities:
- `add_common_args(parser)` -- adds `-t`/`--target` and `-p`/`--profile`
- `add_limit_arg(parser)` -- adds `-l`/`--limit`
- `resolve_profile_and_target(args, require_target=True, validate_npm=False)` -- replaces the duplicated 20-30 line profile resolution block in all 6 modules. Returns `(effective_profile, profile_data, profile_manager)`.
- `resolve_show_target(args)` -- shared show-mode target resolution for pypi/npm

Centralizes `load_dotenv()` and `DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")`.

### Step 3: Create `src/pyf/aggregator/cli.py` (NEW)

Unified entry point using argparse subparsers:
- `build_parser()` -- creates top-level parser with 6 subcommands
- Each subcommand registered with its specific arguments + shared args via `cli_utils`
- Each subcommand's `set_defaults(func=_run_<name>)` calls the module's `run_command(args)`
- `main()` -- parses args, dispatches to subcommand handler

### Step 4: Refactor each module -- extract `run_command(args)`

For each of the 6 modules, split `main()` into:
- `run_command(args)` -- the business logic (receives pre-parsed args), uses `cli_utils.resolve_profile_and_target()`
- `main()` -- thin wrapper: `args = parser.parse_args(); run_command(args)` (kept temporarily for tests, removed later)

Modules to modify:
- `src/pyf/aggregator/main.py` -- extract run_command, use cli_utils for profile resolution
- `src/pyf/aggregator/npm_main.py` -- same, with `validate_npm=True`
- `src/pyf/aggregator/typesense_util.py` -- same, with `require_target=False` (many operations don't need target)
- `src/pyf/aggregator/enrichers/github.py` -- same
- `src/pyf/aggregator/enrichers/downloads.py` -- same
- `src/pyf/aggregator/enrichers/health_calculator.py` -- same

### Step 5: Update `pyproject.toml`

Replace 6 entry points with single:
```toml
[project.scripts]
pyfa = "pyf.aggregator.cli:main"
```

### Step 6: Update tests

**`tests/test_cli_default_profile.py`** (major rewrite):
- Tests currently mock `sys.argv` with old command names and call `module.main()`
- Refactor to call `module.run_command(args)` directly with constructed `argparse.Namespace` objects
- Update class names and docstrings to reference new `pyfa` subcommands
- Profile source logging tests need to patch `cli_utils` instead of module-level variables

**`tests/test_integration_profiles.py`**:
- Update `sys.argv` mocking from `["pyfaggregator", ...]` to use `run_command()` pattern

**`tests/test_cli.py`** (NEW):
- Test unified CLI parser routes correctly to subcommands
- Test `cli_utils.resolve_profile_and_target()` function
- Test `cli_utils.resolve_show_target()` function

### Step 7: Update references in source code

- `src/pyf/aggregator/npm_main.py` -- module docstring references `pyfnpm`
- `src/pyf/aggregator/queue.py` -- comment references `pyfaggregator` (line 989), sincefile name `.pyfaggregator.monthly` (line 1025)
- `src/pyf/aggregator/fetcher.py` -- default sincefile `.pyfaggregator` (line 39)
- `src/pyf/aggregator/plugins/__init__.py` -- comment references `pyfhealth` (line 8)
- `tests/conftest.py` -- sincefile reference `.pyfaggregator` (lines 436, 593)

### Step 8: Update `README.md`

Replace all CLI command documentation with `pyfa` subcommand equivalents.

### Step 9: Run tests and fix

```bash
uv run pytest -v
```

## Files Summary

| File | Action |
|---|---|
| `src/pyf/aggregator/cli.py` | CREATE |
| `src/pyf/aggregator/cli_utils.py` | CREATE |
| `src/pyf/aggregator/main.py` | MODIFY -- extract `run_command(args)` |
| `src/pyf/aggregator/npm_main.py` | MODIFY -- extract `run_command(args)` |
| `src/pyf/aggregator/typesense_util.py` | MODIFY -- extract `run_command(args)` |
| `src/pyf/aggregator/enrichers/github.py` | MODIFY -- extract `run_command(args)` |
| `src/pyf/aggregator/enrichers/downloads.py` | MODIFY -- extract `run_command(args)` |
| `src/pyf/aggregator/enrichers/health_calculator.py` | MODIFY -- extract `run_command(args)` |
| `pyproject.toml` | MODIFY -- single entry point |
| `tests/test_cli_default_profile.py` | MODIFY -- use `run_command()` pattern |
| `tests/test_integration_profiles.py` | MODIFY -- update argv mocking |
| `tests/test_cli.py` | CREATE -- test unified parser + cli_utils |
| `README.md` | MODIFY -- update all command references |
| `src/pyf/aggregator/queue.py` | MODIFY -- update comment references |
| `src/pyf/aggregator/plugins/__init__.py` | MODIFY -- update comment |

## Special Considerations

- **`pyfa manage` is unique**: Many operations (`-ls`, `-lsa`, etc.) don't need a target collection. Use `require_target=False` and validate per-operation.
- **Celery queue.py**: The sincefile defaults (`.pyfaggregator`, `.pyfaggregator.monthly`) are runtime data file names, not CLI commands. Rename to `.pyfa` and `.pyfa.monthly` for consistency, but note this means existing sincefile state will reset on first run.
- **Module-level parsers**: Keep in each module temporarily so `main()` still works for tests during transition. Clean up after test migration.

## Verification

1. `uv run pytest -v` -- all tests pass
2. `uv run pyfa --help` -- shows all subcommands
3. `uv run pyfa pypi --help` -- shows pypi-specific args
4. `uv run pyfa npm --help` -- shows npm-specific args
5. `uv run pyfa manage --help` -- shows manage-specific args
6. Verify old commands no longer exist: `pyfaggregator` should fail
