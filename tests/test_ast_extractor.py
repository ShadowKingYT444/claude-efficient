import ast
from pathlib import Path

def extract_rich_desc(path: Path) -> str:
    if path.suffix != ".py":
        return ""
    
    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        
        docstring = ast.get_docstring(tree) or ""
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        funcs = [node.name for node in tree.body if isinstance(node, ast.FunctionDef) and not node.name.startswith('_')]
        
        parts = []
        if docstring:
            # Get first line of docstring
            first_line = docstring.strip().split('\n')[0][:80]
            parts.append(first_line)
            
        symbols = []
        if classes:
            symbols.append(f"Classes: {', '.join(classes[:3])}")
        if funcs:
            symbols.append(f"Funcs: {', '.join(funcs[:3])}")
            
        if symbols:
            parts.append(f"[{' | '.join(symbols)}]")
            
        return " ".join(parts) if parts else ""
    except Exception as e:
        return f"Parse error: {e}"

def main():
    files = [
        "src/claude_efficient/cli/audit.py",
        "src/claude_efficient/cli/ce_codex.py",
        "src/claude_efficient/cli/ce_router.py",
        "src/claude_efficient/generators/orchestrator.py"
    ]
    
    for f in files:
        p = Path(f)
        desc = extract_rich_desc(p)
        print(f"{p.name}: {desc}")

if __name__ == "__main__":
    main()
