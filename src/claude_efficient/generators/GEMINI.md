# src/claude_efficient/generators

This subdirectory houses the core logic for generating content, specifically for the `claude_efficient` project. It implements a multi-phase approach to project understanding and summarization, aiming for efficiency and determinism.

*   **`backends.py`**: Defines abstractions for helper backends used in phases 1 and 2, along with their provider implementations.
*   **`claudeignore.py`**: Handles logic related to `.claudeignore` files, likely for excluding specific files or directories from processing.
*   **`claude_md.py`**: Implements `ClaudeMdGenerator`, responsible for deterministic generation of Markdown output in phase 4, avoiding direct raw file content paths.
*   **`extractor.py`**: In phase 4, this file focuses on deterministic extraction of project facts without reading file contents.
*   **`fallbacks.py`**: Provides deterministic fallback functions for each `HelperTask`, ensuring no errors are raised.
*   **`mcp.py`**: Implements relevance classification logic for "MCP" (likely a specific type of task or component) in phase 5.
*   **`orchestrator.py`**: Contains the safe-auto orchestration layer, acting as a central coordinator in phase 3.
*   **`prompt.py`**: Handles prompt normalization and classification of task shapes in phase 5.
*   **`selector.py`**: Contains the backend selection logic for phase 2.
*   `tasks_md.py`: Likely defines structures or logic for generating Markdown related to tasks.
*   `__init__.py`: Standard Python initialization file for the package.