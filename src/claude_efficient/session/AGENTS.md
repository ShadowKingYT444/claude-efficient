This subdirectory is responsible for managing and routing sessions within the Claude Efficient system, particularly focusing on efficient model usage and planning.

*   `compact_manager.py`: Manages the efficient storage and retrieval of session data, likely by compacting or serializing it.
*   `mcp_config.py`: Contains configuration settings related to the Model Coordination Protocol (MCP) or similar multi-model communication mechanisms.
*   `mcp_pruner.py`: Implements logic for pruning or optimizing the usage of models within an MCP-based session.
*   `model_router.py`: Handles the routing of requests or tasks to the most appropriate Claude model based on various criteria.
*   `subagent_planner.py`: Manages the planning and coordination of sub-agents within a session, likely for more complex tasks.
*   `__init__.py`: Initializes the `session` module, making its components available for import.