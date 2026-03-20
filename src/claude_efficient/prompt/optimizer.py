# src/claude_efficient/prompt/optimizer.py
from __future__ import annotations

import re
from dataclasses import dataclass, field

FILLER_PATTERNS = [
    # Politeness/hedging — adds zero information
    r"\bplease\s+",
    r"\bcan you\s+",
    r"\bcould you\s+",
    r"\bwould you\s+",
    r"\bi want you to\s+",
    r"\bi need you to\s+",
    r"\bi would like you to\s+",
    r"\bi'd like you to\s+",
    r"\bmake sure to\s+",
    r"\bdon't forget to\s+",
    r"\bgo ahead and\s+",
    r"\bfeel free to\s+",
    # Narration triggers — only strip when used as sequence markers (comma required).
    # Without comma they may be adjectives: "the first file", "the next step" → preserve.
    r"\bfirst,\s+",
    r"\bthen,\s+",
    r"\bfinally,\s+",
    r"\bnext,\s+",
    r"\bafter that,\s+",
    # Reference to prior discussion — already in context
    r"\bas we discussed[,\s]+",
    r"\bas mentioned[,\s]+",
    r"\bas i said[,\s]+",
    r"\blike i said[,\s]+",
    r"\bas noted[,\s]+",
    # Filler adverbs — guard "just" after negation ("not just X" ≠ "not X")
    r"(?<!not )(?<!n't )\bjust\s+",
    r"\bbasically\s+",
    r"\bsimply\s+",
    r"\bessentially\s+",
    r"\bactually\s+",
    r"\breally\s+",
    # Verbose phrasing → shorter equivalent
    r"\bin order to\b",           # → "to"
    r"\bfor the purpose of\b",    # → "to"
    r"\bwith respect to\b",       # → "for"/"about"
    r"\bat this point in time\b", # → "now"
    r"\bdue to the fact that\b",  # → "because"
]

# Replacements for verbose multi-word phrases → concise equivalents
PHRASE_REPLACEMENTS = [
    (r"\bin order to\b", "to"),
    (r"\bfor the purpose of\b", "to"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bat this point in time\b", "now"),
    (r"\bwith respect to\b", "re"),
    (r"\bin the event that\b", "if"),
    (r"\bon the other hand\b", "alternatively"),
    (r"\bas a result of\b", "from"),
]

OUTPUT_FORMAT_HINT = "\nOutput: code only, no preamble."

# Tokens that carry task intent: filenames, dotted paths, snake_case, CamelCase, method()
_INTENT_RE = re.compile(
    r"\b\w+\.\w+\b"          # file.ext, module.attr
    r"|\b\w+_\w+\b"          # snake_case identifiers
    r"|\b[A-Z][a-z]+[A-Z]\w*\b"  # CamelCase
    r"|\b\w+\(\)"            # function()
)


def _intent_preserved(original: str, rewritten: str) -> tuple[bool, list[str]]:
    """Return (preserved, lost) where lost lists technical tokens dropped by rewriting."""
    orig = {m.lower() for m in _INTENT_RE.findall(original)}
    rewr = {m.lower() for m in _INTENT_RE.findall(rewritten)}
    lost = sorted(orig - rewr)
    return (len(lost) == 0, lost)


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

    # Replace verbose phrases with concise equivalents
    for pattern, replacement in PHRASE_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Safety: verify no technical identifiers (filenames, snake_case, CamelCase) were dropped
    preserved, lost_tokens = _intent_preserved(prompt, cleaned)
    if not preserved:
        cleaned = prompt  # revert — whitespace collapse only below
        warnings.append(
            f"Rewrite skipped — optimizer would drop: {', '.join(lost_tokens[:3])}. "
            "Check prompt for ambiguous filler words overlapping identifiers."
        )

    # Collapse whitespace
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

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
