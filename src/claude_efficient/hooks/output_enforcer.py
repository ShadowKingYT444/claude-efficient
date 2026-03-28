"""Hook system for enforcing output token discipline.

Writes to .claude/settings.json with hooks that reinforce output rules:
1. PreCompact: Re-inject critical context (already exists in claude_md.py)
2. UserPromptSubmit: Prepend output format reminder to every user message
"""
from __future__ import annotations

import json
from pathlib import Path

# Brief reminder injected on every user prompt submission.
# Keeps output discipline top-of-mind without burning many tokens.
OUTPUT_REMINDER = "[Output: code only. No explanation. No preamble. No postamble.]"


def write_enforcer_hooks(root: Path) -> Path:
    """Add hooks to .claude/settings.json that help enforce output discipline.

    Merges with existing settings — never overwrites existing hooks.
    Returns the settings file path.
    """
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(exist_ok=True)

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    hooks = existing.setdefault("hooks", {})

    # UserPromptSubmit: inject output format reminder
    if "UserPromptSubmit" not in hooks:
        hooks["UserPromptSubmit"] = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"echo '{OUTPUT_REMINDER}'",
                    }
                ]
            }
        ]

    settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return settings_path
