# Claude Thoughts: Why CE Isn't Saving Enough Tokens & How to Reach 95%

## Executive Summary

CE currently has **7 token-saving mechanisms** but most are either shallow (saving chars, not tokens), dead code (never wired into the CLI), or fundamentally misunderstand where tokens are actually burned. The core problem: **CE optimizes the wrong layer**. It trims prompt text (~50-200 chars) while ignoring the real token sinks: output verbosity (~60% of cost), tool call overhead (~15%), and redundant file reads (~10%). To reach 95% efficiency, CE needs to attack **output tokens** (the largest controllable cost), **system prompt bloat**, and **context window utilization** -- not just input prompt filler words.

---

## Part 1: The Diagnosis -- Why Savings Are Low

### Problem 1: The Prompt Optimizer Saves Almost Nothing

**File:** `src/claude_efficient/prompt/optimizer.py`

The optimizer strips filler words like "please", "can you", "basically" from the user's task prompt. On a typical 80-word prompt, this saves 5-15 words = 20-60 chars = **~5-15 tokens**.

But the user's task prompt is maybe **50-200 tokens** out of a session that burns **50,000-200,000 tokens total**. The optimizer is working on 0.1% of the token budget. Even if it cut the prompt in half, the overall savings would be ~0.05%.

**The math:**
- Typical session: 150,000 total tokens
- User prompt: ~150 tokens
- Optimizer savings: ~15 tokens
- Actual savings: 15/150,000 = **0.01%**

This is the equivalent of saving $0.01 on a $100 bill. It's not zero, but it's why the gains dashboard shows low numbers.

### Problem 2: Telemetry Only Captures Token Data in Pipe Mode

**File:** `src/claude_efficient/cli/session.py` (lines 247-284 vs 286-297)

In `--pipe` mode, CE gets actual `input_tokens`, `output_tokens`, and `cache_read_input_tokens` from Claude's JSON output. But in **interactive mode** (the default, and what most users use), CE gets **zero token data**. It only records `chars_saved` from the prompt optimizer.

This means the `ce gains` dashboard is measuring:
- **Pipe mode:** Real cache hit rates (actually useful)
- **Interactive mode:** Just the filler-word savings from the optimizer (meaningless)

Most users run `ce run "task"` which is interactive. Their gains dashboard shows tiny savings because the only metric available is chars_saved from stripping "please" and "basically". The real savings from prompt caching, CLAUDE.md front-loading, and MCP pruning are **happening but invisible**.

### Problem 3: The Biggest Token Sink is Unmeasured and Uncontrolled -- Output Tokens

Claude's output tokens are typically **60-70% of the cost** in a coding session. CE does literally nothing about this beyond appending `"\nOutput: code only, no preamble."` to the prompt. That hint is routinely ignored by Claude in interactive mode because:

1. The system prompt already has stronger formatting instructions
2. Claude's own personality/training overrides single-line hints
3. The hint is at the very end of the prompt, where attention is weakest

The SESSION_RULES in CLAUDE.md say "Code only. No narration." but these are buried in the generated file and compete with Claude's built-in behaviors. There is **no enforcement mechanism** -- CE fires and forgets.

### Problem 4: Dead Code -- Half the Savings Features Are Never Called

The codebase has significant implemented-but-unreachable functionality:

| Feature | File | Status | Potential Impact |
|---------|------|--------|-----------------|
| `CompactManager.check()` | `compact_manager.py` | Never called at runtime | HIGH -- could auto-suggest /clear at 45% context |
| `SubagentPlanner` | `subagent_planner.py` | Never called from CLI | HIGH -- parallel execution = fewer tokens per task |
| `TasksMdGenerator` | `tasks_md.py` | Never called from CLI | MEDIUM -- task tracking reduces re-exploration |
| `classify_task_shape()` | `prompt.py` | Never called anywhere | MEDIUM -- could inform smarter routing |
| `McpConfigAdvisor.write_session_mcp_json()` | `mcp_config.py` | Not used by `ce run` | LOW -- pruner handles this |
| `inject_model_flag()` | `model_router.py` | Not used by session.py | LOW -- session.py builds cmd directly |

The CompactManager and SubagentPlanner are the two biggest missed opportunities. CompactManager could prevent the most expensive waste pattern (long sessions with degraded context), and SubagentPlanner could dramatically reduce per-task token usage by parallelizing independent file operations.

### Problem 5: CLAUDE.md Generation is Too Generic

**File:** `src/claude_efficient/generators/claude_md.py`, `extractor.py`

The generated CLAUDE.md has useful structure (commands, languages, file tree) but lacks the **specific, surgical information** that actually prevents token waste:

**What it generates:**
```markdown
## Structure
src/
tests/
pyproject.toml

## Languages
python

## Commands
- run: `ce`
- test: `pytest tests/ -x`
```

**What would actually save tokens:**
```markdown
## Architecture (read this, don't explore)
- API layer: src/api/routes.py (FastAPI, 12 endpoints)
- Business logic: src/services/ (5 files, all pure functions)
- DB: src/models/ (SQLAlchemy, PostgreSQL)
- Auth: src/auth/jwt.py (JWT tokens, refresh flow in refresh.py)

## Don't Read These Files (>500 lines, not useful for most tasks)
- src/generated/schema.py (auto-generated, 2000 lines)
- src/migrations/ (alembic, historical only)

## Common Patterns
- All endpoints use `@router.post` with Pydantic models
- Error handling: raise HTTPException, caught by middleware
- Tests mirror src/ structure: tests/test_<module>.py
```

The first version requires Claude to still explore to understand what things do. The second version **eliminates exploration entirely** for most tasks. Each prevented file read saves 1,500-3,000 tokens.

### Problem 6: No Output Token Control

CE has zero mechanisms to control output verbosity. In a typical session:

- Claude explains what it's about to do (~200 tokens, wasted)
- Claude reads a file and summarizes it (~300 tokens, wasted)
- Claude writes code with inline commentary (~30% overhead)
- Claude explains what it just did (~200 tokens, wasted)

Per turn, that's ~500-700 wasted output tokens. Over a 20-turn session: **10,000-14,000 wasted tokens**. This is more than the entire user prompt combined.

The `SESSION_RULES` say "Code only. No narration." but this is a suggestion buried in CLAUDE.md, not an enforced constraint. Claude Code has no mechanism to enforce output constraints, but the prompt engineering can be **much** more aggressive.

### Problem 7: No Hooks Integration

Claude Code supports hooks (`PreToolUse`, `PostToolUse`, `PreCompact`, etc.) that can intercept and modify behavior at runtime. CE writes exactly one hook (PreCompact) that re-injects CLAUDE.md content.

Missing hooks that would save tokens:
- **PreToolUse for Read:** Intercept file reads and inject cached summaries instead
- **PostToolUse for Bash:** Strip verbose command output before it hits context
- **PreCompact:** Already exists but only injects 2 files; could inject a full session summary
- **Stop hook (via CLAUDE.md rules):** Enforce "don't explain, just do it" at the instruction level

### Problem 8: The Savings Metric Itself is Misleading

**File:** `src/claude_efficient/cli/gains.py`

The efficiency formula in gains.py:
```python
tokens_saved = prompt_tokens_saved + cache_tokens_saved
total_baseline = total_input + total_cache_read + prompt_tokens_saved
efficiency_pct = (tokens_saved / total_baseline) * 100.0
```

This conflates two unrelated things:
1. `prompt_tokens_saved` = chars_saved // 4 (tiny, from optimizer)
2. `cache_tokens_saved` = cache_read * 0.95 (huge, from Anthropic's caching)

The cache savings are **not caused by CE**. Anthropic's prompt caching happens automatically when the system prompt + CLAUDE.md prefix is identical across turns. CE's contribution is keeping that prefix stable (by not switching models), which is good but would happen anyway if the user just... doesn't switch models.

The metric makes CE look more effective than it is by claiming credit for Anthropic's built-in caching.

---

## Part 2: Where Tokens Actually Go (The Real Budget)

In a typical 20-turn Claude Code interactive session:

| Category | Tokens | % of Total | CE Addresses? |
|----------|--------|-----------|---------------|
| System prompt + CLAUDE.md | 8,000-15,000 | ~8% | Partially (CLAUDE.md size check) |
| MCP server schemas | 5,000-20,000 | ~10% | Yes (MCP pruning) |
| Tool call overhead per turn | 500-1,000 x 20 = 10,000-20,000 | ~12% | No |
| File reads (input) | 2,000-5,000 x 5 = 10,000-25,000 | ~15% | Partially (CLAUDE.md maps) |
| Claude's output (code + explanation) | 1,000-3,000 x 20 = 20,000-60,000 | ~35% | Barely (one line hint) |
| Redundant context (re-reading files) | 5,000-15,000 | ~8% | No |
| Cache overhead (repeated prefix) | Variable | ~12% | Yes (model stability) |

CE is primarily attacking the 8% (system prompt) and 10% (MCP schemas) categories. The 35% output category and 15% file-read category are almost untouched. The 12% tool overhead is completely untouched.

---

## Part 3: Implementation Plan to Reach 95% Efficiency

### Fix 1: Output Token Suppression System (Expected Impact: 25-35% savings)

**The single highest-impact change.** Output tokens are the largest controllable cost and CE does almost nothing about them.

#### 1A: Aggressive System Prompt Engineering

Replace the current gentle `SESSION_RULES`:
```python
# Current (easily ignored)
SESSION_RULES = """\
## Session rules
- Code only. No preamble. No narration. One file per response.
- Never switch models mid-session (invalidates prompt cache).
- Prefer /clear + new session over /compact at natural breakpoints.
- Do not re-read files already shown in this conversation."""
```

With a **structurally enforced** output format:

```python
SESSION_RULES = """\
## MANDATORY OUTPUT FORMAT (violations waste tokens = waste money)

### Response Structure (EVERY response must follow this)
1. Tool calls OR code blocks. Nothing else.
2. NO explanations before code. NO summaries after code.
3. NO "Let me...", "I'll...", "Here's...", "Now I'll..." preamble.
4. NO "I've completed...", "This should...", "The changes..." postamble.
5. If asked to explain: bullet points only, max 3 bullets, max 15 words each.

### File Operations
- Before reading ANY file: check if its path+purpose is documented below.
  If documented, skip the read unless you need exact line numbers.
- Never re-read a file already shown in this conversation.
- Never read files listed in "Skip These Files" section.
- Batch all related file reads into one turn.

### Code Output
- Write the minimal diff. Don't rewrite unchanged code.
- No comments explaining what the code does (the code IS the explanation).
- No type annotations unless the project already uses them.
- No docstrings unless the project already has them.

### Session Management
- Never switch models mid-session (invalidates prompt cache).
- Prefer /clear + new session over /compact.
- If you've made 3+ tool calls without writing code, stop exploring and start writing."""
```

This is not just different wording -- it's **structured rules with observable violations**. Each rule targets a specific waste pattern the waste_detector already identifies.

#### 1B: Hook-Based Output Enforcement

Create a new module `src/claude_efficient/hooks/output_enforcer.py` that writes additional Claude Code hooks:

```python
"""
Hook system for enforcing output token discipline.

Writes to .claude/settings.json with hooks that:
1. PreCompact: Re-inject critical context (already exists)
2. PostToolUse: Monitor for wasteful patterns and inject reminders

The PostToolUse hooks can't modify Claude's output directly,
but they CAN inject system messages that remind Claude of the rules
if it starts narrating or re-reading files.
"""
```

The implementation:

```python
# src/claude_efficient/hooks/output_enforcer.py
from __future__ import annotations
import json
from pathlib import Path

# Hook that fires after every tool use to track session state
POST_TOOL_USE_TRACKER = {
    "type": "command",
    "command": (
        "python3 -c \""
        "import json, sys; "
        "data = json.load(sys.stdin); "
        "tool = data.get('tool_name', ''); "
        "# Track consecutive reads without writes; "
        "# Output warning if exploration is excessive "
        "\""
    ),
}

def write_enforcer_hooks(root: Path) -> None:
    """
    Add hooks to .claude/settings.json that help enforce output discipline.

    Current hooks:
    - PreCompact: Re-inject CLAUDE.md + TASKS.md (already exists)
    - UserPromptSubmit: Prepend output format reminder to every user message
    """
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(exist_ok=True)

    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except Exception:
            pass

    hooks = existing.setdefault("hooks", {})

    # The UserPromptSubmit hook can prepend a brief reminder
    # This is lighter than modifying system prompts
    if "UserPromptSubmit" not in hooks:
        hooks["UserPromptSubmit"] = [{
            "hooks": [{
                "type": "command",
                "command": "echo '[Output: code only. No explanation. No preamble.]'"
            }]
        }]

    settings_path.write_text(json.dumps(existing, indent=2))
```

#### 1C: Context-Aware Output Budgeting

Add output token budgets to the session based on task complexity:

```python
# src/claude_efficient/session/output_budget.py
"""
Estimate appropriate output budget for a task and encode it in the prompt.

Token budget heuristics:
- Single file edit: ~500 output tokens max
- Multi-file refactor: ~2000 output tokens max
- New feature: ~3000 output tokens max
- Explanation request: ~300 output tokens max

Claude won't enforce these hard limits, but including them in the prompt
creates a strong prior toward concise output.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class OutputBudget:
    estimated_tokens: int
    hint: str

def estimate_output_budget(task: str, file_count: int = 1) -> OutputBudget:
    """Compute suggested output token budget based on task analysis."""
    lower = task.lower()

    # Explanation tasks should be ultra-short
    if any(w in lower for w in ["explain", "what does", "how does", "why"]):
        return OutputBudget(300, "Max 3 bullet points, 15 words each.")

    # Bug fixes are usually small diffs
    if any(w in lower for w in ["fix", "bug", "error", "broken", "failing"]):
        return OutputBudget(500 * file_count, f"Minimal diff only. ~{file_count} file(s).")

    # Refactors touch more files but shouldn't over-explain
    if any(w in lower for w in ["refactor", "rename", "move", "reorganize"]):
        return OutputBudget(800 * file_count, f"Diffs only, {file_count} file(s). No narration.")

    # New features are larger
    if any(w in lower for w in ["add", "create", "build", "implement", "new"]):
        return OutputBudget(2000 * min(file_count, 3), "Code blocks only. No step-by-step.")

    # Default
    return OutputBudget(1000, "Be concise. Code only where possible.")

def format_budget_hint(budget: OutputBudget) -> str:
    """Format as a prompt suffix."""
    return f"\n[Output budget: ~{budget.estimated_tokens} tokens. {budget.hint}]"
```

Wire into `session.py` between prompt optimization and final prompt assembly:

```python
# In session.py run(), after optimize() and before building final_prompt:
from claude_efficient.session.output_budget import estimate_output_budget, format_budget_hint

budget = estimate_output_budget(opt.text, scope.estimated_files if has_task else 1)
opt_text_with_budget = opt.text + format_budget_hint(budget)
```

### Fix 2: Smart File Read Prevention (Expected Impact: 10-15% savings)

The biggest input token sink after system prompts is Claude reading files to understand the codebase. If CLAUDE.md contains enough architectural information, many reads become unnecessary.

#### 2A: Deep Architecture Extraction

Replace the shallow `_scan_tree()` (which just lists top-level entries) with a multi-level architecture extractor:

```python
# src/claude_efficient/generators/architecture.py
"""
Deep architecture extraction for CLAUDE.md generation.

Instead of listing files, this module extracts:
1. Module purposes (from docstrings, __init__.py, class/function names)
2. Dependency graph (which modules import which)
3. Entry points and data flow
4. Common patterns (decorator usage, base classes, error handling)
5. Files that should NOT be read (generated, large, historical)

The goal: Claude should be able to make most edits WITHOUT reading
any files first, because CLAUDE.md tells it exactly where things are
and what patterns to follow.
"""
from __future__ import annotations
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class ModuleInfo:
    path: str
    purpose: str           # One-line description from docstring or inference
    public_api: list[str]  # Exported classes/functions
    imports_from: list[str] # Internal modules this depends on
    line_count: int
    complexity: str        # "trivial" | "simple" | "moderate" | "complex"

@dataclass
class ArchitectureMap:
    layers: dict[str, list[ModuleInfo]]  # e.g. {"api": [...], "services": [...]}
    entry_points: list[str]
    common_patterns: list[str]
    skip_files: list[str]              # Files Claude should never read
    dependency_flow: list[str]         # e.g. ["api -> services -> models -> db"]

def extract_architecture(root: Path) -> ArchitectureMap:
    """
    Walk the project and build a high-level architecture map.

    This is more expensive than extract_facts() but produces
    dramatically more useful CLAUDE.md content. Run during ce init only.
    """
    modules = _discover_modules(root)
    layers = _classify_into_layers(modules)
    entry_points = _find_entry_points(modules)
    patterns = _detect_common_patterns(root, modules)
    skip_files = _find_skip_candidates(root, modules)
    dep_flow = _build_dependency_flow(layers)

    return ArchitectureMap(
        layers=layers,
        entry_points=entry_points,
        common_patterns=patterns,
        skip_files=skip_files,
        dependency_flow=dep_flow,
    )

def _discover_modules(root: Path) -> list[ModuleInfo]:
    """Extract ModuleInfo from every Python file via AST analysis."""
    modules = []
    for py_file in root.rglob("*.py"):
        if any(skip in py_file.parts for skip in {
            "__pycache__", ".git", "node_modules", ".venv", "venv",
            "dist", "build", ".egg-info", "migrations"
        }):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)

            # Extract docstring
            docstring = ast.get_docstring(tree) or ""
            purpose = docstring.split("\n")[0][:100] if docstring else ""

            # If no docstring, infer from class/function names
            if not purpose:
                purpose = _infer_purpose(tree, py_file.name)

            # Extract public API
            public = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    public.append(f"class {node.name}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        public.append(f"{node.name}()")

            # Extract internal imports
            imports_from = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if not node.module.startswith(("os", "sys", "re", "json", "typing")):
                        imports_from.append(node.module)

            line_count = len(content.splitlines())
            complexity = (
                "trivial" if line_count < 30 else
                "simple" if line_count < 100 else
                "moderate" if line_count < 300 else
                "complex"
            )

            modules.append(ModuleInfo(
                path=str(py_file.relative_to(root)),
                purpose=purpose,
                public_api=public[:10],
                imports_from=imports_from,
                line_count=line_count,
                complexity=complexity,
            ))
        except Exception:
            continue

    return modules

def _infer_purpose(tree: ast.Module, filename: str) -> str:
    """Infer module purpose from its contents when no docstring exists."""
    classes = [n.name for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
    functions = [n.name for n in ast.iter_child_nodes(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    if classes:
        return f"Defines {', '.join(classes[:3])}"
    if functions:
        return f"Contains {', '.join(functions[:3])}"
    return f"Module: {filename}"

def _classify_into_layers(modules: list[ModuleInfo]) -> dict[str, list[ModuleInfo]]:
    """Group modules into architectural layers based on path and content."""
    layer_hints = {
        "api": ["api", "routes", "endpoints", "views", "handlers"],
        "cli": ["cli", "commands", "main"],
        "services": ["services", "logic", "core", "domain"],
        "models": ["models", "schemas", "entities", "types"],
        "data": ["db", "database", "repository", "dao", "store"],
        "utils": ["utils", "helpers", "common", "shared"],
        "config": ["config", "settings", "constants"],
        "tests": ["tests", "test_"],
    }

    layers: dict[str, list[ModuleInfo]] = {}
    for mod in modules:
        path_lower = mod.path.lower()
        assigned = False
        for layer, hints in layer_hints.items():
            if any(h in path_lower for h in hints):
                layers.setdefault(layer, []).append(mod)
                assigned = True
                break
        if not assigned:
            layers.setdefault("other", []).append(mod)

    return layers

def _find_entry_points(modules: list[ModuleInfo]) -> list[str]:
    """Find likely entry points (main functions, CLI commands, app factories)."""
    entry_points = []
    for mod in modules:
        for api in mod.public_api:
            if any(name in api.lower() for name in ["main", "cli", "app", "run", "start"]):
                entry_points.append(f"{mod.path}:{api}")
    return entry_points[:10]

def _detect_common_patterns(root: Path, modules: list[ModuleInfo]) -> list[str]:
    """Detect recurring patterns Claude should follow."""
    patterns = []

    # Check for common decorators
    decorator_counts: dict[str, int] = {}
    for py_file in root.rglob("*.py"):
        if any(skip in py_file.parts for skip in {"__pycache__", ".venv", "venv"}):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            for match in re.findall(r"@(\w+(?:\.\w+)*)", content):
                decorator_counts[match] = decorator_counts.get(match, 0) + 1
        except Exception:
            continue

    common_decorators = [(d, c) for d, c in decorator_counts.items() if c >= 3]
    if common_decorators:
        top = sorted(common_decorators, key=lambda x: -x[1])[:5]
        patterns.append(f"Common decorators: {', '.join(f'@{d} ({c}x)' for d, c in top)}")

    # Check for base classes
    # Check for error handling patterns
    # etc. -- extend as needed

    return patterns

def _find_skip_candidates(root: Path, modules: list[ModuleInfo]) -> list[str]:
    """Find files Claude should never bother reading."""
    skip = []
    for mod in modules:
        if mod.line_count > 500:
            skip.append(f"{mod.path} ({mod.line_count} lines, {mod.complexity})")
        if any(kw in mod.path.lower() for kw in ["generated", "migration", "vendor", "lock"]):
            skip.append(f"{mod.path} (auto-generated/vendored)")

    # Also flag non-Python large files
    for f in root.rglob("*"):
        if f.is_file() and f.suffix in {".json", ".lock", ".svg", ".min.js"}:
            try:
                size = f.stat().st_size
                if size > 50_000:
                    skip.append(f"{f.relative_to(root)} ({size // 1024}KB, skip)")
            except Exception:
                continue

    return skip[:20]

def _build_dependency_flow(layers: dict[str, list[ModuleInfo]]) -> list[str]:
    """Build simplified dependency flow arrows."""
    flows = []
    layer_order = ["api", "cli", "services", "models", "data", "config"]
    present = [l for l in layer_order if l in layers]
    if len(present) >= 2:
        flows.append(" -> ".join(present))
    return flows

def render_architecture_md(arch: ArchitectureMap) -> str:
    """Render the architecture map as CLAUDE.md content."""
    lines = []

    if arch.dependency_flow:
        lines.append("## Architecture Flow")
        for flow in arch.dependency_flow:
            lines.append(f"  {flow}")
        lines.append("")

    for layer_name, modules in arch.layers.items():
        if layer_name == "tests":
            continue  # Don't describe test files in detail
        lines.append(f"## {layer_name.title()} Layer")
        for mod in sorted(modules, key=lambda m: m.path):
            api_str = f" -- exports: {', '.join(mod.public_api[:5])}" if mod.public_api else ""
            lines.append(f"- `{mod.path}`: {mod.purpose}{api_str}")
        lines.append("")

    if arch.entry_points:
        lines.append("## Entry Points")
        for ep in arch.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("")

    if arch.common_patterns:
        lines.append("## Patterns to Follow")
        for p in arch.common_patterns:
            lines.append(f"- {p}")
        lines.append("")

    if arch.skip_files:
        lines.append("## Skip These Files (don't read unless specifically asked)")
        for sf in arch.skip_files:
            lines.append(f"- {sf}")
        lines.append("")

    return "\n".join(lines)
```

#### 2B: File Read Cache in Session Context

Track which files Claude has already read and inject a reminder:

```python
# src/claude_efficient/hooks/read_tracker.py
"""
Track file reads during a session to prevent redundant reads.

Uses a PreToolUse hook on the Read tool to check if the file
has already been read. If so, injects a reminder with the
file's purpose from CLAUDE.md instead of blocking the read.

This doesn't prevent the read (can't do that via hooks), but
the injected context often causes Claude to skip the read itself.
"""
```

### Fix 3: Wire Up Dead Code (Expected Impact: 10-15% savings)

#### 3A: Activate CompactManager in Interactive Sessions

The CompactManager has good logic for detecting when context is degrading, but it's never called. Wire it into the interactive session loop.

The challenge: in interactive mode, CE doesn't have visibility into context usage (Claude doesn't expose it). But we can estimate it.

```python
# In session.py, add a post-session analysis step:

def _post_session_analysis(root: Path, duration: float, model: str) -> None:
    """
    After an interactive session ends, estimate what happened.

    We can't monitor context mid-session, but we can:
    1. Check the session transcript if it was logged
    2. Estimate based on duration (longer = more context used)
    3. Provide recommendations for next session
    """
    # If duration > 10 minutes, likely hit context limits
    if duration > 600:
        click.secho(
            "[ce] Long session detected. Consider splitting future tasks "
            "and using /clear between logical units.",
            fg="yellow",
        )

    # Run waste detector on any available transcript
    transcript = root / ".claude" / "last-session.log"
    if transcript.exists():
        from claude_efficient.analysis.waste_detector import WasteDetector
        report = WasteDetector().run(transcript)
        if report.findings:
            click.secho(f"[ce] Post-session audit found {len(report.findings)} issue(s):", fg="yellow")
            for f in report.findings[:3]:
                click.secho(f"  - {f.category}: ~{f.tokens_wasted:,} tokens", fg="yellow")
```

#### 3B: Activate SubagentPlanner for Multi-File Tasks

When the scope analyzer detects a multi-file task, offer to parallelize:

```python
# In session.py, after scope analysis:

if scope.will_require_compact and not pipe:
    from claude_efficient.session.subagent_planner import SubagentPlanner, extract_file_targets

    planner = SubagentPlanner()
    targets = extract_file_targets(opt.text)

    if planner.should_parallelize(opt.text) and len(targets) >= 2:
        click.secho(
            f"[ce] Multi-file task detected ({len(targets)} files). "
            f"Running parallel subagents to reduce total tokens...",
            fg="cyan",
        )

        # Build file tasks and execute in waves
        from claude_efficient.session.subagent_planner import FileTask
        tasks = [FileTask(target_file=t) for t in targets]
        waves = planner.build_waves(tasks)

        for i, wave in enumerate(waves):
            click.echo(f"[ce] Wave {i+1}/{len(waves)}: {[t.target_file for t in wave]}")
            results = planner.execute_wave(wave, model=chosen_model)
            for r in results:
                status = "ok" if r.success else "FAILED"
                click.echo(f"  [{status}] {r.file}")

        return  # Skip normal session -- work is done
```

#### 3C: Wire classify_task_shape into Model Router

Use task shape classification to make smarter routing decisions:

```python
# Enhanced model_router.py

def route(task_prompt: str, task_shape: str | None = None) -> RoutingDecision:
    """Route based on both keywords AND task shape."""
    lowered = task_prompt.lower()

    # Shape-based routing (more accurate than keyword matching)
    if task_shape:
        if task_shape in ("explain", "system_design"):
            return RoutingDecision(model=OPUS, reason=f"task shape: {task_shape}")
        if task_shape in ("file_edit", "new_file"):
            return RoutingDecision(model=SONNET, reason=f"task shape: {task_shape}")

    # Fallback to keyword matching
    for trigger in OPUS_TRIGGERS:
        if trigger in lowered:
            return RoutingDecision(model=OPUS, reason=f"keyword: '{trigger}'")

    return RoutingDecision(model=SONNET, reason="implementation task")
```

### Fix 4: Real Telemetry for Interactive Mode (Expected Impact: Measurement, not direct savings)

Without measuring interactive mode properly, we can't prove or improve savings. This fix makes the gains dashboard trustworthy.

#### 4A: Post-Session Token Extraction

After an interactive session ends, query Claude Code's internal logs for token usage:

```python
# src/claude_efficient/analysis/session_parser.py
"""
Parse Claude Code session data after an interactive session completes.

Claude Code stores session data in ~/.claude/projects/<hash>/sessions/.
After a session ends, we can read the conversation JSON to extract
actual token usage that wasn't available during the session.
"""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class SessionTokens:
    total_input: int
    total_output: int
    total_cache_read: int
    turn_count: int
    tools_used: dict[str, int]  # tool_name -> count

def parse_last_session(project_root: Path) -> SessionTokens | None:
    """
    Find and parse the most recent Claude Code session for this project.

    Claude Code stores sessions under:
    ~/.claude/projects/<project_hash>/sessions/<session_id>.jsonl

    Each line is a conversation turn with token usage metadata.
    """
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    # Find the project directory (hashed by path)
    # Claude Code uses the project path to create a hash
    project_str = str(project_root.resolve())

    # Search all project dirs for the most recent session
    latest_session = None
    latest_mtime = 0.0

    for project_dir in claude_dir.iterdir():
        sessions_dir = project_dir / "sessions"
        if not sessions_dir.exists():
            continue
        for session_file in sessions_dir.glob("*.jsonl"):
            mtime = session_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_session = session_file

    if latest_session is None:
        return None

    return _parse_session_file(latest_session)

def _parse_session_file(path: Path) -> SessionTokens:
    """Parse a Claude Code session JSONL file for token usage."""
    total_input = 0
    total_output = 0
    total_cache = 0
    turn_count = 0
    tools: dict[str, int] = {}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            usage = data.get("usage", {})
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)
            total_cache += usage.get("cache_read_input_tokens", 0)

            if data.get("role") == "assistant":
                turn_count += 1

            # Track tool usage
            tool_use = data.get("tool_use", {})
            tool_name = tool_use.get("name", "")
            if tool_name:
                tools[tool_name] = tools.get(tool_name, 0) + 1
        except (json.JSONDecodeError, AttributeError):
            continue

    return SessionTokens(
        total_input=total_input,
        total_output=total_output,
        total_cache_read=total_cache,
        turn_count=turn_count,
        tools_used=tools,
    )
```

Wire into `_write_telemetry` for interactive mode:

```python
# In session.py, after interactive subprocess completes:
from claude_efficient.analysis.session_parser import parse_last_session

session_data = parse_last_session(root_path)
if session_data:
    _write_telemetry(
        root_path, task_text, opt,
        mode="interactive", model=chosen_model,
        actual_input=session_data.total_input,
        actual_output=session_data.total_output,
        actual_cache=session_data.total_cache_read,
        duration=duration,
    )
```

#### 4B: Fix the Gains Metric

Replace the misleading combined metric with separate, honest metrics:

```python
# In gains.py, replace the single efficiency metric with:

# Metric 1: CE-attributed savings (what CE actually caused)
ce_prompt_savings = prompt_tokens_saved  # From optimizer
ce_mcp_savings = sum(r.mcp_tokens_saved or 0 for r in records)  # New field
ce_output_savings = sum(r.output_tokens_saved or 0 for r in records)  # New field
ce_total_savings = ce_prompt_savings + ce_mcp_savings + ce_output_savings

# Metric 2: Cache efficiency (Anthropic's caching, helped by CE's stability)
if total_cache_read > 0 and total_input > 0:
    cache_hit_rate = total_cache_read / (total_input + total_cache_read) * 100
else:
    cache_hit_rate = 0.0

# Metric 3: Overall cost efficiency vs naive usage
# Naive = no caching, no optimization, Opus for everything
naive_cost = (total_input + total_cache_read) * 15 + total_output * 75  # per million
actual_cost = total_input * 3 + total_cache_read * 0.30 + total_output * 15  # Sonnet pricing
cost_savings_pct = (1 - actual_cost / naive_cost) * 100 if naive_cost > 0 else 0
```

### Fix 5: Smarter CLAUDE.md with Anti-Exploration Directives (Expected Impact: 8-12% savings)

#### 5A: Generate "Don't Explore" Sections

When generating CLAUDE.md, explicitly list what Claude should NOT do:

```python
# Add to claude_md.py's generation:

def _generate_anti_exploration(facts: ExtractedFacts, arch: ArchitectureMap) -> str:
    """Generate directives that prevent wasteful exploration."""
    lines = ["## What NOT To Do (each violation wastes ~1,500 tokens)\n"]

    # Don't read generated files
    if arch.skip_files:
        lines.append("### Don't Read These Files")
        for f in arch.skip_files[:10]:
            lines.append(f"- {f}")
        lines.append("")

    # Don't explore directories that are well-documented
    lines.append("### Don't Explore (use the map above instead)")
    lines.append("- Don't `ls` or `find` to discover project structure -- it's documented above")
    lines.append("- Don't read __init__.py files -- they're usually empty or just imports")
    lines.append("- Don't read test files to understand implementation -- read the source")
    lines.append("- Don't grep for imports -- the dependency flow is documented above")
    lines.append("")

    # Common wasteful patterns to avoid
    lines.append("### Don't Waste Output Tokens")
    lines.append("- Don't summarize files after reading them")
    lines.append("- Don't explain code changes unless asked")
    lines.append("- Don't list what you're about to do -- just do it")
    lines.append("- Don't show full file contents -- show only the changed lines")

    return "\n".join(lines)
```

#### 5B: Dynamic CLAUDE.md Based on Task Type

Instead of one static CLAUDE.md, generate task-specific context:

```python
# src/claude_efficient/generators/task_context.py
"""
Generate task-specific CLAUDE.md supplements.

Instead of loading the entire project map for every task,
generate a focused supplement based on what the task needs.

Example: "fix the login bug" only needs auth module context,
not the entire project architecture.
"""

def generate_task_supplement(task: str, arch: ArchitectureMap) -> str:
    """
    Given a task prompt and the full architecture, produce a minimal
    context document that contains ONLY what the task needs.

    This replaces the per-subdirectory CLAUDE.md approach with
    something more surgical.
    """
    relevant_modules = _find_relevant_modules(task, arch)

    lines = [f"## Task-Relevant Context\n"]
    for mod in relevant_modules:
        lines.append(f"### {mod.path}")
        lines.append(f"Purpose: {mod.purpose}")
        if mod.public_api:
            lines.append(f"API: {', '.join(mod.public_api[:5])}")
        if mod.imports_from:
            lines.append(f"Depends on: {', '.join(mod.imports_from[:3])}")
        lines.append("")

    return "\n".join(lines)

def _find_relevant_modules(task: str, arch: ArchitectureMap) -> list:
    """Find modules relevant to the task using keyword matching."""
    task_lower = task.lower()
    relevant = []

    for layer_modules in arch.layers.values():
        for mod in layer_modules:
            # Check if task mentions anything related to this module
            path_parts = mod.path.lower().replace("/", " ").replace("_", " ").replace(".py", "")
            if any(part in task_lower for part in path_parts.split() if len(part) > 3):
                relevant.append(mod)
            elif any(api.lower().rstrip("()") in task_lower for api in mod.public_api):
                relevant.append(mod)

    return relevant[:10]  # Cap at 10 most relevant modules
```

### Fix 6: Tool Call Overhead Reduction (Expected Impact: 5-8% savings)

Every tool call has overhead: the tool schema, the call parameters, and the result formatting. CE currently does nothing about this.

#### 6A: Batch Tool Call Encouragement

Add instructions to CLAUDE.md that encourage batching:

```python
# Add to SESSION_RULES:

BATCH_RULES = """
### Tool Call Discipline
- Batch file reads: read all needed files in ONE turn (parallel tool calls)
- Don't read a file just to check one thing -- grep for it instead
- Don't run tests after every small change -- batch changes, test once
- If a command fails, fix the root cause; don't retry the same command
- Prefer Edit over Write for existing files (smaller diffs = fewer tokens)
"""
```

#### 6B: Pre-Load Frequently Needed Files

For common operations, inject file contents directly into the prompt so Claude doesn't need tool calls:

```python
# src/claude_efficient/generators/preloader.py
"""
Pre-load files that Claude will almost certainly need for a given task.

Instead of letting Claude discover it needs a file, read it, and then act,
we inject the most-likely-needed file contents directly into the session
context. This trades a small increase in input tokens for elimination of
tool call round-trips (each round-trip has ~500 tokens of overhead).
"""

def preload_for_task(task: str, root: Path) -> dict[str, str]:
    """Return {path: content} of files Claude will likely need."""
    files = {}
    task_lower = task.lower()

    # If task mentions a specific file, preload it
    import re
    mentioned = re.findall(
        r"([\w./\\-]+\.(?:py|js|ts|tsx|go|rs|toml|json|yaml|yml))", task
    )
    for path in mentioned[:3]:
        full = root / path
        if full.is_file():
            content = full.read_text(encoding="utf-8", errors="ignore")
            if len(content) < 5000:  # Don't preload huge files
                files[path] = content

    # If task is about tests, preload the test config
    if any(w in task_lower for w in ["test", "spec", "pytest"]):
        for cfg in ["pytest.ini", "pyproject.toml", "jest.config.js", "vitest.config.ts"]:
            full = root / cfg
            if full.is_file():
                files[cfg] = full.read_text(encoding="utf-8", errors="ignore")[:2000]
                break

    return files
```

### Fix 7: Honest Cost Dashboard (Expected Impact: Transparency)

Replace the current gains.py with a dashboard that shows **real numbers** and **actionable insights**:

```python
# Redesigned gains output:

"""
CE Token Savings (Global)
========================

Sessions tracked: 47 (32 interactive, 15 pipe)

ACTUAL SAVINGS (caused by CE):
  Prompt optimization:     842 tokens saved   (0.1% of total)
  MCP pruning:           14,200 tokens saved   (2.3% of total)
  Output suppression:    31,500 tokens saved   (5.1% of total)  [NEW]
  File read prevention:  18,400 tokens saved   (3.0% of total)  [NEW]
  ────────────────────────────────────────────
  CE total:              64,942 tokens saved   (10.5% of total)

CACHE EFFICIENCY (Anthropic's caching, CE helps maintain):
  Cache hit rate:        87.3% (target: >85%)
  Cache-assisted cost:   $2.14 (vs $12.80 without caching = 83% savings)

OVERALL COST EFFICIENCY:
  Without CE:            $18.40 (Opus, no caching, exploration overhead)
  With CE:                $1.67 (Sonnet, cached, optimized)
  Total savings:          90.9%

TOP WASTE PATTERNS (fixable):
  1. Claude narration: ~8,400 tokens across 12 sessions
     Fix: Strengthen CLAUDE.md output rules
  2. Redundant file reads: ~5,200 tokens across 8 sessions
     Fix: Run `ce init --deep` for better architecture map
  3. Long sessions without /clear: ~3,100 tokens across 3 sessions
     Fix: Use separate `ce run` calls for each task
"""
```

---

## Part 4: Priority Order

| Priority | Fix | Expected Impact | Effort | Dependencies |
|----------|-----|----------------|--------|-------------|
| **P0** | Fix 1: Output token suppression | 25-35% | Medium | None |
| **P1** | Fix 2: Smart architecture extraction | 10-15% | High | None |
| **P1** | Fix 3A: Wire CompactManager | 5-8% | Low | None |
| **P2** | Fix 4A: Interactive mode telemetry | Measurement | Medium | None |
| **P2** | Fix 4B: Fix gains metric | Transparency | Low | Fix 4A |
| **P2** | Fix 5: Anti-exploration CLAUDE.md | 8-12% | Medium | Fix 2 |
| **P3** | Fix 6: Tool call optimization | 5-8% | Medium | Fix 2 |
| **P3** | Fix 3B: Wire SubagentPlanner | 5-10% | Medium | None |
| **P3** | Fix 7: Honest dashboard | Transparency | Low | Fix 4 |

**Combined realistic ceiling: ~80-90%**

Why not 95%? Some overhead is irreducible:
- System prompt tokens (~5,000) are always needed
- CLAUDE.md itself costs tokens to load
- Tool calls have inherent structural overhead
- Some file reads are genuinely necessary
- Claude's output can be compressed but not eliminated

To hit 95%, you'd need model-level changes (not possible) or to move most work to pipe mode (which has limited capability). **85-90% with interactive mode is the realistic ceiling**, and that's excellent.

---

## Part 5: What's Actually Working Well

Credit where due -- these parts of CE are solid:

1. **Model routing** -- Simple, correct, prevents the #1 cache-killer (model switching)
2. **MCP pruning** -- Well-implemented, significant savings for users with many MCP servers
3. **Cache health checks** -- Catches real configuration mistakes before they waste tokens
4. **Prompt caching stability** -- By setting the env flag and keeping models stable, CE ensures Anthropic's caching works optimally
5. **CLAUDE.md generation** -- The concept is right, execution just needs to go deeper
6. **PreCompact hook** -- Smart idea to re-inject critical context during compaction
7. **.claudeignore** -- Prevents Claude from reading binary/build artifacts

The foundation is good. The problem is that CE stops at the "prevent obvious mistakes" level and doesn't push into the "actively compress the conversation" level.

---

## Part 6: Architecture Recommendations

### Current Architecture
```
User prompt -> optimize (strip filler) -> route (pick model) -> launch Claude
                                                                     |
                                                              (uncontrolled session)
                                                                     |
                                                              session ends -> record chars_saved
```

### Target Architecture
```
User prompt -> analyze task shape -> compute output budget -> optimize prompt
     |              |                        |                      |
     |              v                        v                      v
     |         preload relevant       inject budget hint      strip filler +
     |         file contents          into prompt              add format rules
     |              |                        |                      |
     |              +------------------------+----------------------+
     |                                       |
     v                                       v
pick model -> assemble full prompt -> launch Claude with hooks
                                           |
                                    [hooks enforce rules]
                                    [track tool usage]
                                    [monitor context %]
                                           |
                                    session ends
                                           |
                                    parse session data -> extract real token usage
                                           |
                                    record comprehensive telemetry
                                           |
                                    post-session audit + recommendations
```

The key difference: the target architecture **wraps the entire session lifecycle**, not just the launch. It knows what happened inside the session and uses that knowledge to improve future sessions.

---

## Appendix: Files to Create/Modify

### New Files
- `src/claude_efficient/generators/architecture.py` -- Deep architecture extraction
- `src/claude_efficient/generators/task_context.py` -- Task-specific context generation
- `src/claude_efficient/generators/preloader.py` -- File preloading for common operations
- `src/claude_efficient/hooks/output_enforcer.py` -- Hook-based output enforcement
- `src/claude_efficient/session/output_budget.py` -- Output token budgeting
- `src/claude_efficient/analysis/session_parser.py` -- Post-session token extraction

### Modified Files
- `src/claude_efficient/generators/claude_md.py` -- Use architecture.py, add anti-exploration
- `src/claude_efficient/cli/session.py` -- Wire CompactManager, SubagentPlanner, output budget, post-session analysis, real telemetry
- `src/claude_efficient/cli/init.py` -- Use deep architecture extraction, write enforcer hooks
- `src/claude_efficient/cli/gains.py` -- Honest multi-metric dashboard
- `src/claude_efficient/session/model_router.py` -- Accept task_shape for smarter routing
- `src/claude_efficient/generators/prompt.py` -- Wire classify_task_shape into session pipeline
- `src/claude_efficient/analysis/telemetry.py` -- Add new fields (mcp_tokens_saved, output_tokens_saved)
