# SPEC_FINAL — CLI Integration + End-to-End Wiring
**Session goal:** Wire all implemented modules into a working `ce` CLI. Every command callable. All tests pass.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md` + this file only. Do NOT read spec files or module implementations.

---

## Context

Gemini has implemented all individual modules. This session's only job is integration:
register commands, fix any import gaps, and verify the whole thing works end-to-end.
Do not rewrite any module logic — only wire, register, and fix broken imports.

---

## Subtask 1 — Audit and fix `cli/main.py`

Replace the full file with this. It registers every command and nothing else:

```python
# src/claude_efficient/cli/main.py
import click

from claude_efficient.cli.audit import audit
from claude_efficient.cli.commands import mem_search, scope_check, status
from claude_efficient.cli.init import init
from claude_efficient.cli.session import run


@click.group()
@click.version_option(package_name="claude-efficient")
def cli() -> None:
    """claude-efficient — token optimization for Claude Code sessions."""


cli.add_command(init)
cli.add_command(run)
cli.add_command(audit)
cli.add_command(mem_search)
cli.add_command(scope_check)
cli.add_command(status)
```

---

## Subtask 2 — Verify `__init__.py` files exist and are non-empty stubs

Check that each of these exists. If missing, create with the content shown.
If it exists already, leave it alone.

```
src/claude_efficient/__init__.py          → __version__ = "0.1.0"
src/claude_efficient/cli/__init__.py      → (empty string is fine)
src/claude_efficient/generators/__init__.py → (empty string is fine)
src/claude_efficient/session/__init__.py  → (empty string is fine)
src/claude_efficient/analysis/__init__.py → (empty string is fine)
src/claude_efficient/prompt/__init__.py   → (empty string is fine)
src/claude_efficient/config/__init__.py   → (empty string is fine)
```

---

## Subtask 3 — Smoke test: `ce --help` and all subcommands

Run each command and confirm exit code 0 and no import errors:

```bash
ce --help
ce init --help
ce run --help
ce audit --help
ce mem-search --help
ce scope-check --help
ce status --help
```

If any command fails with `ImportError` or `ModuleNotFoundError`:
- Read only the failing `cli/*.py` file
- Fix the broken import path (do not rewrite the module)
- Re-run until all 7 pass

---

## Subtask 4 — Fix `config/defaults.toml` path resolution

The `mcp_pruner.py` and `mcp_config.py` both load `defaults.toml` using
`Path(__file__).parent.parent / "config" / "defaults.toml"`. Verify this resolves
correctly from the installed package path. If the file isn't found at runtime, add
a `find_defaults_toml()` helper to `config/__init__.py`:

```python
# src/claude_efficient/config/__init__.py
from pathlib import Path

def find_defaults_toml() -> Path:
    """Return path to defaults.toml, works both installed and in dev mode."""
    candidates = [
        Path(__file__).parent / "defaults.toml",
        Path(__file__).parent.parent / "config" / "defaults.toml",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("defaults.toml not found — reinstall package")
```

Then update any module that uses the hardcoded path to use `find_defaults_toml()` instead.
Only fix if the path is actually broken — don't touch working code.

---

## Subtask 5 — Integration smoke test

```bash
# Real end-to-end test — run from the project root
ce status                                           # should not crash
ce scope-check "Build auth.py and user.py"          # should print estimate
ce run "print hello world" --dry-run                # should print model + plan, no crash
ce audit nonexistent.log                            # should print "file not found" cleanly
```

All four must complete without Python tracebacks.

---

## Subtask 6 — Full test suite

```bash
pytest tests/ -x --tb=short
ruff check src/
```

If a test fails:
- Read only the failing test file and the module it tests
- Fix the module, not the test
- Exception: if the test was written for a removed feature (e.g., `tasks_md.py` or
  `ce update-tasks`), delete that test file — the feature was intentionally removed

---

## Acceptance criteria
- [ ] `ce --help` shows: init, run, audit, mem-search, scope-check, status
- [ ] All 6 subcommands respond to `--help` without ImportError
- [ ] `ce run "x" --dry-run` prints model selection and plan
- [ ] `ce status` prints health dashboard without crash
- [ ] `pytest tests/ -x` passes
- [ ] `ruff check src/` passes

## Done
```bash
ce --help
pytest tests/ -x
```