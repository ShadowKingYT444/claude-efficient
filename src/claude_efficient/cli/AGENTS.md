This subdirectory `src/claude_efficient/cli` contains the command-line interface (CLI) components for the Claude Efficient project. It provides tools to interact with and manage various code generation models through a unified interface.

- `audit.py`: (Description not provided)
- `ce_cursor.py`: Provides a thin, CE-compatible wrapper for Cursor. As Cursor lacks native headless mode, running it opens an interactive session.
- `ce_gemini.py`: Offers a thin, CE-compatible wrapper for the Gemini CLI, supporting headless mode with `gemini -p`.
- `ce_opencode.py`: Contains a thin, CE-compatible wrapper for the OpenCode CLI, with headless mode activated by `opencode run`.
- `ce_router.py`: Acts as a router, delegating calls like `--cli <name> --cmd <init|run|status>` to the appropriate CE-compatible CLI wrappers.
- `ce_wrapper_core.py`: (Description not provided)
- `commands.py`: (Description not provided)
- `gains.py`: (Description not provided)
- `helpers.py`: Introduces the `ce helpers` subcommand, which allows for inspection of provider status and configuration.
- `init.py`: The initialization script for the CLI.
- `main.py`: The main entry point for the Claude Efficient CLI application.
- `session.py`: (Description not provided)
- `__init__.py`: (Description not provided)