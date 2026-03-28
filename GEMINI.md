# Project GEMINI: Claude Efficient (CE)

This project provides a framework for optimizing AI agent sessions, focusing on token efficiency and context preservation across multiple LLMs, including Gemini via the `ce-gemini` wrapper.

## Project Goal
The goal of Claude Efficient is to **optimize the "first turn" experience** and maximize prompt caching. For Gemini, this means utilizing the `ce-gemini` entry point (pointing to `src/claude_efficient/cli/ce_gemini.py`) to apply the same prompt normalization and character-level optimization used for Claude.

## Implementation Status

### Core CLI Support
- **`ce-gemini`**: A CE-compatible wrapper for the Gemini CLI (`src/claude_efficient/cli/ce_gemini.py`). It uses the `gemini -p` command for headless, optimized execution.
- **`ce init`**: Generates a `GEMINI.md` alongside `CLAUDE.md`, providing a consistent codebase map for you when you are invoked within a CE-managed project.

### Key Logic
- `src/claude_efficient/cli/ce_router.py`: This is the central routing agent that delegates `--cli gemini` commands to the appropriate wrapper.
- `src/claude_efficient/generators/claude_md.py`: Implements `ClaudeMdGenerator.write_gemini_md()`, which ensures that Gemini receives a mirrored version of the project's documentation.

## Current Audit & Roadmap

### What's Working
- **Initialization**: `ce init` correctly builds `GEMINI.md` and `.geminiignore` (using `ClaudeignoreGenerator` in `src/claude_efficient/generators/claudeignore.py`).
- **Telemetry**: Gemini usage is tracked in the global `~/.ce-telemetry.jsonl` file via `src/claude_efficient/analysis/telemetry.py`.
- **`ce-gemini` Wrapper**: A CE-compatible wrapper for the Gemini CLI (`src/claude_efficient/cli/ce_gemini.py`) that uses `gemini -p` for headless, optimized execution with automatic approval.
- **Gemini-Specific Scaffolding**: Refine `src/claude_efficient/generators/claude_md.py` to optionally output Gemini-optimized system instructions in `GEMINI.md`.
- **Memory Support**: Integrate `claude-mem` (cross-session memory) more natively into the `ce-gemini` execution flow.
