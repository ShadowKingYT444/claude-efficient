# Project: claude-efficient

A CLI tool for optimizing token usage in Claude Code sessions. It acts as a wrapper around the `claude` CLI, applying various strategies to reduce token consumption and improve session efficiency.

## Core Concepts

The tool's main goal is to minimize token cost by:
1.  **Automated Context Generation:** Creating a concise `CLAUDE.md` (and `GEMINI.md`) with a project summary, file map, and key file contexts, using a free/local LLM backend to avoid costs during initialization. It supports `@import` for subdirectories to keep the root context file small.
2.  **Session Wrapping (`ce run`):** Intercepting `claude` sessions to apply pre-flight checks and optimizations.
3.  **Post-Hoc Analysis (`ce audit`):** Analyzing session transcripts to identify and report on token-wasting patterns.
4.  **Intelligent Session Management:** Providing proactive advice on model selection, context size (`/compact`), and tool (MCP) configuration.
5.  **Cross-Session Memory:** Integrating with `claude-mem` to inject relevant context from past sessions.

## Project Structure

### 1. `cli/` - Command-Line Interface

-   **`main.py`**: Entry point for the `ce` command using `click`.
-   **`init.py` (`ce init`)**: Initializes a project. Generates `CLAUDE.md`, `.claudeignore`, and a PreCompact hook. Performs cache health checks.
-   **`session.py` (`ce run`)**: The core command. Wraps a `claude` session to:
    -   Perform cache health checks.
    -   Optimize the user's prompt.
    -   Estimate the task's token scope.
    -   Route to the most cost-effective model (Opus vs. Sonnet).
    -   Advise on MCP server overhead.
    -   Inject a memory brief from `claude-mem`.
-   **`audit.py` (`ce audit`)**: Analyzes session transcripts for waste.
-   **`commands.py`**: Implements supplementary commands like `ce status`, `ce mem-search`, and `ce scope-check`.

### 2. `analysis/` - Session & Project Analysis

-   **`waste_detector.py`**: Powers the `audit` command. Contains logic to detect patterns like unnecessary file reads, bash retries, large pastes, overuse of expensive models, and cache invalidation events.
-   **`cache_health.py`**: Performs static, pre-session checks to identify configuration issues that could harm prompt caching efficiency, such as large context files or suboptimal MCP server setup.

### 3. `generators/` - Context File Generation

-   **`claude_md.py`**: Generates the `CLAUDE.md` and `GEMINI.md` files. It uses a `Backend` to summarize the project structure.
-   **`backends.py`**: Defines abstract `Backend` classes for LLMs used in analysis. It prioritizes free/local models like Gemini CLI and Ollama to ensure `ce init` is free.
-   **`claudeignore.py`**: Creates `.claudeignore` and `.geminiignore` files.
-   **`tasks_md.py`**: Manages a `TASKS.md` file for project tracking.

### 4. `prompt/` - Prompt Engineering

-   **`optimizer.py`**: Cleans and optimizes user prompts by removing filler phrases and flagging anti-patterns like vagueness or multi-tasking.

### 5. `session/` - In-Session Strategy & Management

-   **`model_router.py`**: Selects the appropriate model for the *entire session* at the start (Opus for architecture, Sonnet for implementation) to prevent cache-invalidating model switches.
-   **`compact_manager.py`**: Provides advice on context window management. It includes a `SessionScopeAnalyzer` to estimate a task's token cost upfront and advises when to use `/compact` or `/clear`.
-   **`mcp_config.py` & `mcp_pruner.py`**: Advise on MCP (Model Context Protocol) server configuration. The key recommendation is to enable an experimental flag (`ENABLE_EXPERIMENTAL_MCP_CLI`) that allows on-demand loading of tool schemas, saving thousands of tokens at session start.
-   **`subagent_planner.py`**: An advanced feature for parallelizing file-based tasks across multiple concurrent `claude` processes.

### 6. Project & Configuration

-   **`pyproject.toml`**: Defines dependencies, project metadata, and the `ce` script entry point.
-   **`config/defaults.toml`**: (Not present but referenced) Provides default settings for the tool.
