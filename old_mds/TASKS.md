# TASKS.md
**Maintained by claude-efficient. Start each session: "See TASKS.md. Build [next item]."**

## Current phase: Phase 4 — Audit + Analysis

## Completed
- [x] SPEC_01: Project scaffold (pyproject.toml, folder structure, Click CLI skeleton)
- [x] SPEC_02: `generators/backends.py` — GeminiBackend, OllamaBackend, LLMBackend, ClaudeBackend
- [x] SPEC_03: `generators/claude_md.py` — ClaudeMdGenerator (file scan + template render)
- [x] SPEC_04: `generators/claudeignore.py` — ClaudeignoreGenerator

## Phase 1 — Architecture Fixes (do before building anything new)
- [x] SPEC_01-04-FIXES: Fix defaults.toml thresholds + always_keep; protect mcp_pruner;
      add @import scaffolding + PreCompact hook to ClaudeMdGenerator

## Phase 2 — Claude-mem Integration + Init
- [x] SPEC_05: `analysis/cache_health.py` — prompt cache health monitor + ENABLE_EXPERIMENTAL_MCP_CLI advisor
- [x] SPEC_06: `cli/init.py` — full `ce init`: claude-mem health check, @import tree, PreCompact hook, claude-mem session brief primer

## Phase 3 — Session Layer (corrected architecture)
- [x] SPEC_07: `session/model_router.py` — session-start-only model selection, never mid-session
- [x] SPEC_08: `session/compact_manager.py` — 45% threshold, prefer /clear, session scope analyzer
- [x] SPEC_09: `session/mcp_config.py` — ENABLE_EXPERIMENTAL_MCP_CLI advisor + always_keep guard (replaces pruner)
- [x] SPEC_10: `prompt/optimizer.py` — filler stripping, anti-patterns, scope estimation
- [x] SPEC_11: `cli/session.py` — `ce run` with claude-mem session brief + cache health pre-check

## Phase 4 — Audit + Analysis
- [x] SPEC_12: `analysis/waste_detector.py` — 7 detectors (6 original + cache invalidation detector)
- [x] SPEC_13: `cli/audit.py` — report formatter + `ce audit` command

## Phase 5 — Subagents + Commands
- [x] SPEC_14: `session/subagent_planner.py` — dependency graph + wave execution
- [x] SPEC_15: `cli/commands.py` — `ce mem-search`, `ce scope-check`, `ce status`

## Phase 6 — Packaging
- [x] SPEC_16: PyPI packaging, README, CI

---
_Last updated: see git log_
