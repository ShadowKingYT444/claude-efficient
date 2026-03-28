import json
from pathlib import Path
from dataclasses import dataclass
from claude_efficient.generators.extractor import extract_facts, _get_file_desc
from claude_efficient.generators.claude_md import _serialize_facts
from test_ast_extractor import extract_rich_desc

# --- Cost Assumptions ---
# A simplified model for token cost calculation.
# In reality, it's more complex, but this captures the dynamic.
BASE_AGENT_CONTEXT_COST = 2000  # Cost of history for each turn
READ_FILE_COST_PER_BYTE = 0.5 # Approximating token cost for file content

@dataclass
class SimulationResult:
    name: str
    gen_cost: int
    agent_turns: int
    agent_cost: int
    total_cost: int
    log: list[str]

def get_file_content_cost(file_path: str) -> int:
    try:
        content = Path(file_path).read_text()
        return int(len(content.encode('utf-8')) * READ_FILE_COST_PER_BYTE)
    except FileNotFoundError:
        return 0

def simulate_agent(task: str, claude_md_content: str) -> tuple[int, list[str]]:
    """Simulates an agent performing a task, returning turns and logs."""
    log = [f"TASK: {task}"]
    turns = 0
    
    # Turn 1: Always read the root CLAUDE.md
    turns += 1
    log.append(f"TURN {turns}: Agent reads CLAUDE.md ({len(claude_md_content)} chars)")

    # Analyze the CLAUDE.md to find the right file
    cli_file_info = ""
    for line in claude_md_content.splitlines():
        if "audit.py" in line:
            cli_file_info = line.strip()
            break
    
    log.append(f"ANALYSIS: Agent sees this info for audit.py: '{cli_file_info}'")

    if not cli_file_info or not "audit" in cli_file_info:
        # If the file isn't even listed, it has to guess
        turns += 1
        log.append(f"TURN {turns}: File 'audit.py' not found or undescribed. Agent must use `grep` or `ls` to find it. (Penalty turn)")
        
    # Does the description give enough info to know the functions and how to implement the change?
    if "run_audit_report" not in cli_file_info or "main entry point is `run_audit_report`" not in cli_file_info:
        # If the key function and its purpose aren't obvious, the agent must read the file
        turns += 1
        log.append(f"TURN {turns}: Description is sparse. Agent must `read_file` on 'src/claude_efficient/cli/audit.py' to understand function signatures and implementation before editing.")
    else:
        log.append("ANALYSIS: Description is rich enough. Agent can proceed to edit without an exploratory read.")

    # Final turn to actually perform the edit (assumed for all)
    turns += 1
    log.append(f"TURN {turns}: Agent performs the edit on the file.")

    return turns, log

def run_comparison():
    """Compares total token cost across different generation strategies."""
    root = Path.cwd()
    facts = extract_facts(root)
    task = "Add a --format option to the audit command that can be either 'json' or 'text'."
    
    results = []
    
    # --- STRATEGY 1: Deterministic (Original) ---
    desc_map_orig = {f.name: _get_file_desc(f) for f in (root / "src/claude_efficient/cli").glob("*.py")}
    md_orig = "# CLI Subdir\n" + "\n".join(f"- {name}: {desc}" for name, desc in desc_map_orig.items())
    turns_orig, log_orig = simulate_agent(task, md_orig)
    agent_cost_orig = (turns_orig * BASE_AGENT_CONTEXT_COST) + get_file_content_cost('src/claude_efficient/cli/audit.py')
    results.append(SimulationResult(
        name="Deterministic (Original)",
        gen_cost=0,
        agent_turns=turns_orig,
        agent_cost=agent_cost_orig,
        total_cost=agent_cost_orig,
        log=log_orig
    ))

    # --- STRATEGY 2: Deterministic (AST) ---
    desc_map_ast = {f.name: extract_rich_desc(f) for f in (root / "src/claude_efficient/cli").glob("*.py")}
    md_ast = "# CLI Subdir\n" + "\n".join(f"- {name}: {desc}" for name, desc in desc_map_ast.items())
    turns_ast, log_ast = simulate_agent(task, md_ast)
    # The agent might still read the file to edit, but it avoids the *exploratory* turn. We assume 1 less turn.
    agent_cost_ast = ((turns_ast) * BASE_AGENT_CONTEXT_COST) + get_file_content_cost('src/claude_efficient/cli/audit.py')
    results.append(SimulationResult(
        name="Deterministic (AST)",
        gen_cost=0,
        agent_turns=turns_ast,
        agent_cost=agent_cost_ast,
        total_cost=agent_cost_ast,
        log=log_ast
    ))
    
    # --- STRATEGY 3: Cheap LLM (Simulated) ---
    gen_cost_llm = 1500  # Estimated cost for a small model to summarize the facts
    md_llm = """
# Subdirectory: src/claude_efficient/cli
This directory contains the command-line interface for the application.

- **audit.py**: Contains the logic for the `audit` command. The main entry point is `run_audit_report`, which takes the project root and reports on potential token waste.
- **main.py**: The main entry point for the CLI application.
- **init.py**: Handles the `ce init` command for setting up a new project.
    """
    turns_llm, log_llm = simulate_agent(task, md_llm)
    agent_cost_llm = (turns_llm * BASE_AGENT_CONTEXT_COST) + get_file_content_cost('src/claude_efficient/cli/audit.py')
    results.append(SimulationResult(
        name="Cheap LLM (Simulated)",
        gen_cost=gen_cost_llm,
        agent_turns=turns_llm,
        agent_cost=agent_cost_llm,
        total_cost=gen_cost_llm + agent_cost_llm,
        log=log_llm
    ))

    # --- Print Results ---
    print("--- Agent Simulation Results ---")
    for res in sorted(results, key=lambda r: r.total_cost):
        print(f"\n--- Strategy: {res.name} ---")
        print(f"  Generation Cost: {res.gen_cost} tokens")
        print(f"  Agent Cost:      {res.agent_cost} tokens ({res.agent_turns} turns)")
        print(f"  TOTAL COST:      {res.total_cost} tokens")
        print("  Agent's Journey:")
        for log_item in res.log:
            print(f"    - {log_item}")

if __name__ == "__main__":
    run_comparison()
