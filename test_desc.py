from pathlib import Path

def _get_file_desc(path: Path) -> str:
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(('"""', "'''")):
                return line.strip(" \"'")[:100]
            if line.startswith(("#", "//", "/*", "*", "<!--")):
                cleaned = line.lstrip("#/ *<!-").strip()
                if cleaned:
                    return cleaned[:100]
            if not line.startswith(("import ", "from ", "package ", "use ")):
                break
    except Exception:
        pass
    return ""

print(_get_file_desc(Path("src/claude_efficient/generators/claude_md.py")))
print(_get_file_desc(Path("src/claude_efficient/generators/extractor.py")))
