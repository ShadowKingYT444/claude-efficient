# Project CLAUDE: Claude Efficient (CE)

This project provides a token-optimization framework for your sessions, ensuring your responses are fast, cost-effective, and highly contextual.

## Core Project Goal
The goal of CE is to **maximize prompt caching and context efficiency** for AI agents. By utilizing CE, you spend fewer tokens navigating and more tokens solving complex architectural problems.

## Your Current Directives
1.  **Cache Preservation**: Adhere to the `SESSION_RULES` in generated `CLAUDE.md` files (e.g., in `src/claude_efficient/generators/claude_md.py`). Specifically:
    - Never switch models mid-session.
    - Prefer `/clear` + new session over `/compact` to reset context correctly.
2.  **Deterministic Scaffolding**: Use `ce init` (implemented in `src/claude_efficient/cli/init.py`) to keep project maps up to date without manual file reading.
3.  **Efficiency First**: Prioritize surgical edits using `replace` and `write_file`.

## Technical Status

### Sub-Packages & Functionality
- `src/claude_efficient/cli/`: Main CLI entry points and orchestration (`main.py`, `session.py`).
- `src/claude_efficient/cli/ce_gemini.py`: Thin wrapper for Gemini CLI.
- `src/claude_efficient/cli/ce_cursor.py`: Thin wrapper for Cursor CLI.
- `src/claude_efficient/cli/ce_opencode.py`: Thin wrapper for OpenCode CLI.
- `src/claude_efficient/generators/`: Logic for project understanding and `.md` generation (`extractor.py`, `claude_md.py`).
- `src/claude_efficient/analysis/`: Tools for identifying token waste and configuration risks (`waste_detector.py`, `cache_health.py`).
- `src/claude_efficient/session/`: Advanced session management like model routing and MCP pruning (`model_router.py`, `mcp_pruner.py`).

### Critical Functions to Reference
- `claude_efficient.cli.session.run()`: The primary entry point for optimized task execution.
- `claude_efficient.analysis.cache_health.CacheHealthMonitor.check_all()`: Run this to diagnose environment issues.
- `claude_efficient.generators.extractor.extract_facts()`: The core "brain" for project understanding.

## Roadmap & Maintenance Tasks
- **Audit Logic Refinement**: Update `src/claude_efficient/analysis/waste_detector.py` to recognize more "inefficient" patterns like repetitive `grep` or `ls` calls.
- **MCP Configuration Advisor**: Expand `src/claude_efficient/session/mcp_config.py` to dynamically adjust the active toolset based on the task description.
- **Cross-Session Memory Integration**: Ensure `claude-mem` is correctly utilized in `src/claude_efficient/cli/session.py` to minimize context rebuilding.
