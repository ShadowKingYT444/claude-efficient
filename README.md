<div align="center">
  <br />
  <h1>Claude Efficient</h1>
  <p>
    <strong>Stop burning Claude Code tokens.</strong>
  </p>
  <p>
    <code>ce</code> wraps every session with automatic optimizations to save you money and improve context quality.
  </p>
</div>

---

## 🚀 Installation

`claude-efficient` is a Python package. Ensure you have Python 3.11+ installed.

```bash
pip install claude-efficient
```

This will install the `ce` command-line tool.

## ✨ Quick Start

1.  **Initialize your project:**
    ```bash
    ce init
    ```
    This command sets up your project with a `CLAUDE.md`, `.claudeignore`, and other necessary configurations for optimal performance.

2.  **Run a task:**
    ```bash
    ce run "Your task description here. For example, build a FastAPI endpoint for user auth."
    ```
    This is the main command you'll use. It automatically optimizes your request, manages session context, and routes it appropriately.

3.  **Check your savings:**
    ```bash
    ce gains
    ```
    This command displays a detailed dashboard of your token savings across different operations.

## 📋 Commands

`claude-efficient` provides a suite of commands to manage your workflow and optimize token usage.

| Command         | Description                                                              |
| --------------- | ------------------------------------------------------------------------ |
| `ce init`       | Initializes a new or existing project for use with `claude-efficient`.   |
| `ce run [TASK]` | Runs a new coding session with the given task, applying optimizations.   |
| `ce gains`      | Displays the token savings dashboard.                                    |
| `ce status`     | Shows a health dashboard for the current project configuration.          |
| `ce audit [LOG]`| Audits a session log to detect inefficiencies and suggest improvements.  |
| `ce telemetry`  | Shows before/after token savings from recorded sessions.                 |
| `ce mem-search` | Searches cross-session memory for relevant context from past tasks.      |
| `ce scope-check`| Estimates the token requirements for a task before running a session.    |
| `ce helpers`    | Provides assistance with setting up helpers and integrations.            |

---
<div align="center">
  <p>Made with ❤️ for efficient coding sessions.</p>
</div>
