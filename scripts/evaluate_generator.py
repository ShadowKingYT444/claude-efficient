import os
from pathlib import Path
from claude_efficient.generators.extractor import extract_facts
from claude_efficient.generators.claude_md import ClaudeMdGenerator

def main():
    root = Path.cwd()
    facts = extract_facts(root)
    gen = ClaudeMdGenerator()
    
    # Generate root CLAUDE.md using deterministic approach (no helper)
    result = gen.generate_root(facts, invoke_helper_fn=None)
    
    print("--- GENERATED CLAUDE.md (ROOT) ---")
    print(result)
    print("--- END ---")
    
    # Calculate sizes
    gen_size = len(result.encode())
    
    # Hypothetical raw list: all files in the project
    all_files = []
    for r, d, fs in os.walk(root):
        if any(skip in r for skip in [".git", "__pycache__", ".venv", "venv", ".ruff_cache"]):
            continue
        for f in fs:
            all_files.append(os.path.join(r, f))
    
    raw_list_size = sum(len(f.encode()) for f in all_files)
    
    print(f"\nGenerated CLAUDE.md size: {gen_size} bytes")
    print(f"Number of files tracked in raw list: {len(all_files)}")
    print(f"Raw list of paths size: {raw_list_size} bytes")
    
    # Find a qualifying subdir to test subdir generation
    qualifying = [c for c in facts.subdir_candidates if c.qualifies]
    if qualifying:
        print(f"\nFound {len(qualifying)} qualifying subdirs.")
        first = qualifying[0]
        subdir_result = gen.generate_subdir(first, invoke_helper_fn=None)
        print(f"--- GENERATED CLAUDE.md (SUBDIR: {first.path}) ---")
        print(subdir_result)
        print("--- END ---")
        print(f"Subdir CLAUDE.md size: {len(subdir_result.encode())} bytes")

if __name__ == "__main__":
    main()
