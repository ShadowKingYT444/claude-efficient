# Claude Efficient (ce-tool)

**Maximize token efficiency and context quality for AI agent sessions.**

`claude-efficient` (invoked as `ce`) is a powerful optimization wrapper for Claude Code and other AI command-line tools. It automatically normalizes prompts, prunes unnecessary context, and tracks token savings to keep your sessions fast, cost-effective, and highly contextual.

## 🚀 Installation

Ensure you have **Python 3.11+** installed.

### Quick Install (Pip)
```bash
pip install ce-tool
```

### From Source
```bash
git clone https://github.com/ShadowKingYT444/claude-efficient.git
cd claude-efficient
pip install -e .
```

## ✨ Core Workflow

### 1. Initialize your project
```bash
ce init
```
Generates optimized project maps (`CLAUDE.md`, `GEMINI.md`) and configuration files to help AI agents understand your codebase without excessive file exploration.

### 2. Run optimized tasks
```bash
ce run "Add a new endpoint to the users API"
```
Automatically applies character-level prompt optimization, model routing, and context management before launching the session.

### 3. Track your savings
```bash
ce gains
```
View a detailed dashboard of token savings, session durations, and cache efficiency across all your projects.

## 🤖 Multi-Agent Support

CE provides drop-in optimization wrappers for other popular AI CLIs, applying the same prompt normalization and telemetry tracking:

- `ce-gemini`: Optimization wrapper for the Google Gemini CLI.
- `ce-cursor`: Optimization wrapper for the Cursor CLI.
- `ce-opencode`: Optimization wrapper for the OpenCode CLI.

## 📋 Available Commands

| Command | Description |
| :--- | :--- |
| `ce init` | Set up a project with optimized context maps. |
| `ce run [TASK]` | Start an optimized AI agent session. |
| `ce gains` | Display the token savings and efficiency dashboard. |
| `ce status` | Check project health and cache optimization status. |
| `ce audit [LOG]` | Analyze session logs for token waste. |
| `ce mem-search` | Search cross-session memory for relevant context. |

---
*Optimizing the way you build with AI.*
