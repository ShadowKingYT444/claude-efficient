# claude-efficient

CLI tool that wraps Claude Code sessions to eliminate token waste. `ce` command.

## Architecture
```
cli/            # main.py (Click group), init.py, session.py, audit.py, commands.py
generators/     # claude_md.py, claudeignore.py, backends.py
session/        # model_router.py, compact_manager.py, mcp_config.py, subagent_planner.py
analysis/       # cache_health.py, waste_detector.py
prompt/         # optimizer.py
config/         # defaults.toml, schema.py
tests/          # mirrors src/ structure
```

## Key files
- `config/defaults.toml` — all thresholds; always_keep guards claude-mem hooks
- `generators/backends.py` — GeminiBackend, OllamaBackend, LLMBackend, ClaudeBackend + detect_backend()
- `generators/claude_md.py` — ClaudeMdGenerator: scan, generate, write, @import tree, PreCompact hook
- `cli/main.py` — Click group; all commands registered here
- `session/model_router.py` — model selected ONCE at session start; inject_model_flag()
- `session/mcp_config.py` — advises on ENABLE_EXPERIMENTAL_MCP_CLI; never removes servers
- `analysis/cache_health.py` — detects prompt cache prefix violations before they happen

## Specs (load the relevant one only — do NOT read all at once)
specs/SPEC_01_04_FIXES.md     # architecture corrections for already-built code
specs/SPEC_05_06_revised.md   # cache_health.py + updated ce init
specs/SPEC_07_11_revised.md   # session layer: router, compact, mcp_config, optimizer, ce run
specs/SPEC_12_16_revised.md   # audit, subagents, commands, packaging

## Architecture constraints (non-negotiable)
- **Model routing is session-start-only.** Switching models mid-session invalidates the
  prompt cache prefix — costing more than running Opus start-to-finish.
- **MCP servers are never removed mid-session.** Use ENABLE_EXPERIMENTAL_MCP_CLI=true
  for on-demand schema loading. always_keep = ["claude_mem", "memory", "filesystem"].
- **claude_mem hooks are not user-invoked tools.** PostToolUse, SessionEnd fire passively.
  Disabling the server kills the capture pipeline; that entire session produces zero memory.
- **Compact threshold: 45%.** Default action is /clear + fresh session, not /compact.
  Two compactions in one session = task was scoped too large.

## Run commands
```bash
pip install -e ".[dev]"
ce --help
pytest tests/ -x
ruff check .
```

## Current phase
See TASKS.md

## Output format
- Code only. No preamble. No "let me first check" narration.
- One file per response unless explicitly asked for multiple.
- Bash verification at the end only, never mid-write.
- Imports at top, no inline explanations inside code.
