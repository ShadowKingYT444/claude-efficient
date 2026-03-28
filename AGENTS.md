# Claude Efficient: Internal Agent & Component Audit

This document details the specialized internal logic and "agent-like" components that power the Claude Efficient (CE) ecosystem.

## Project Goal
The primary objective of Claude Efficient is to **drastically reduce the operational cost and latency of AI-driven coding sessions** while simultaneously increasing the accuracy of generated code. It achieves this by:
1.  **Context Optimization**: Minimizing the tokens consumed by project-level instructions through deterministic scaffolding (`CLAUDE.md`).
2.  **Session Hygiene**: Preventing model switching and upfront tool loading that invalidates prompt caching.
3.  **Intelligence Augmentation**: Integrating cross-session memory (`claude-mem`) to provide long-term project context without manual re-explanation.

## Current Component Status

### 1. Initialization & Scaffolding (`ce init`)
- **Status**: **STABLE**.
- **Logic**: Located in `src/claude_efficient/cli/init.py`. It coordinates the `ClaudeMdGenerator` and `Extractor` to build a project map.
- **Key Functions**:
    - `_check_claude_mem()`: Verifies if the long-term memory worker is active on port 37777.
    - `_build_import_block()`: Handles large projects by splitting documentation into root and subdirectory `CLAUDE.md` files, using the `@import` pattern to keep root context under 2KB.

### 2. Session Orchestration (`ce run`)
- **Status**: **STABLE**.
- **Logic**: Located in `src/claude_efficient/cli/session.py`. This is the main entry point for optimized sessions.
- **Key Functions**:
    - `normalize_prompt()`: Uses helper LLMs (Gemini/Ollama) to strip conversational filler from tasks.
    - `optimize()`: Performs character-level compression of prompts (see `src/claude_efficient/prompt/optimizer.py`).
    - `_build_pipe_context()`: For `--pipe` mode, injects `CLAUDE.md` and referenced file contents into a single-turn request for rapid execution.

### 3. Analysis & Verification
- **Cache Health**: `src/claude_efficient/analysis/cache_health.py` identifies risks like missing `ENABLE_EXPERIMENTAL_MCP_CLI` flags or oversized `CLAUDE.md` files.
- **Waste Detector**: `src/claude_efficient/analysis/waste_detector.py` audits session logs to identify "toxic" token patterns like redundant file reads or narration.
- **Telemetry**: `src/claude_efficient/analysis/telemetry.py` tracks performance metrics to prove ROI (Target: >50% token savings).

### 4. Planning & Routing
- **Model Router**: `src/claude_efficient/session/model_router.py` selects the most efficient model (Sonnet vs. Haiku) based on task complexity.
- **MCP Pruner**: `src/claude_efficient/session/mcp_pruner.py` suggests disabling unused tools to save upfront schema tokens.
- **Subagent Planner**: `src/claude_efficient/session/subagent_planner.py` (EXPERIMENTAL) handles topological sorting of multi-file tasks for parallel execution.

## Roadmap & Critical Tasks

### High Priority
1.  **Refine Audit Accuracy**: Enhance `WasteDetector.run()` in `src/claude_efficient/analysis/waste_detector.py` to better estimate "billed vs. cached" tokens in interactive sessions.
2.  **Interactive Health Warnings**: Integrate `SessionScopeAnalyzer.estimate()` from `src/claude_efficient/session/compact_manager.py` more tightly into the start of `ce run` to warn when a task is too large for a single context window.
3.  **MCP Pruning Automation**: Transition `McpPruner` from an advisory tool to an automated configuration generator that temporarily updates `.mcp.json` before a session.

### Medium Priority
1.  **Improved Subagent Interface**: Robustify `SubagentPlanner.execute_wave()` to handle partial failures and better context-sharing between parallel subagents.
2.  **Helper Backend Expansion**: Add support for more local backends in `src/claude_efficient/generators/backends.py` to ensure prompt optimization remains "off-band" and free.
