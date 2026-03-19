# src/claude_efficient/prompt/optimizer.py
from __future__ import annotations

import re
from dataclasses import dataclass, field

FILLER_PATTERNS = [
    r"\bplease\s+",
    r"\bcan you\s+",
    r"\bi want you to\s+",
    r"\bi need you to\s+",
    r"\bmake sure to\s+",
    r"\bdon't forget to\s+",
    r"\bas we discussed[,\s]+",
    r"\bjust\s+",
    r"\bgo ahead and\s+",
    r"\bfeel free to\s+",
]

OUTPUT_FORMAT_HINT = "\nOutput: code only, no preamble."


@dataclass
class OptimizedPrompt:
    text: str
    warnings: list[str] = field(default_factory=list)
    chars_saved: int = 0


def optimize(prompt: str) -> OptimizedPrompt:
    warnings: list[str] = []
    original_len = len(prompt)

    # Strip filler phrases
    cleaned = prompt
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"  +", " ", cleaned).strip()

    # Anti-pattern: vague prompt
    if len(cleaned.split()) < 6:
        warnings.append(
            "Vague prompt — add: target file, what to change, expected behavior."
        )

    # Anti-pattern: massive paste (likely spec content)
    if len(cleaned) > 1_500:
        warnings.append(
            "Long prompt (>1,500 chars). Move spec content to CLAUDE.md or "
            "use `#filename` to reference a file without pasting it."
        )

    # Anti-pattern: multi-task in one prompt
    if cleaned.count(" and ") > 2 or cleaned.count(",") > 4 or "\n-" in cleaned:
        warnings.append(
            "Multi-task prompt — split into separate `ce run` calls. "
            "Each call gets a clean context; combined calls pollute each other."
        )

    # Add output hint if not already present
    if "output:" not in cleaned.lower() and "code only" not in cleaned.lower():
        cleaned += OUTPUT_FORMAT_HINT

    return OptimizedPrompt(
        text=cleaned,
        warnings=warnings,
        chars_saved=original_len - len(cleaned),
    )
