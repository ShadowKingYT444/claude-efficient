from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    category: str
    severity: str  # "low" | "medium" | "high" | "critical"
    tokens_wasted: int
    fix: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class WasteReport:
    findings: list[Finding]
    total_tokens: int
    waste_tokens: int
    billed_tokens: int | None = None
    cache_read_tokens: int | None = None

    @property
    def waste_pct(self) -> float:
        return self.waste_tokens / self.total_tokens if self.total_tokens else 0.0


class WasteDetector:
    TOOL_PATTERN = re.compile(
        r'"tool_name"\s*:\s*"([^"]+)"'
        r'|tool[_\s-]*name\s*[:=]\s*([A-Za-z0-9_.-]+)'
        r'|\b(?:Tool|tool)\s*[:=]\s*([A-Za-z0-9_.-]+)',
        re.IGNORECASE,
    )
    COMMAND_PATTERN = re.compile(r'"command"\s*:\s*"([^"]+)"', re.IGNORECASE)

    def detect_file_reads(self, transcript: str) -> Finding | None:
        reads = len(re.findall(r"(Read \d+ file|let me (check|look at|read))", transcript, re.I))
        if reads < 3:
            return None
        return Finding(
            "unnecessary_file_reads",
            "high",
            reads * 600,
            "Add codebase map to CLAUDE.md — Claude won't need to navigate.",
            [f"{reads} file-read operations detected"],
        )

    def detect_bash_retries(self, transcript: str) -> Finding | None:
        retries = len(
            re.findall(r"(ModuleNotFoundError|No module named|Exit code 1.*retry)", transcript)
        )
        if retries < 2:
            return None
        return Finding(
            "bash_retry_loops",
            "medium",
            retries * 400,
            "Add run/test commands to CLAUDE.md.",
            [f"{retries} failed bash attempts"],
        )

    def detect_repetitive_tool_calls(self, transcript: str) -> Finding | None:
        raw_tools: list[str] = []
        for match in self.TOOL_PATTERN.findall(transcript):
            raw_tools.extend(value for value in match if value)

        tools = [self._normalize_signature(name) for name in raw_tools if name.strip()]
        repeated_tools = Counter(tools)
        hot_tools = [(name, count) for name, count in repeated_tools.items() if count >= 3]

        commands = [
            self._normalize_signature(cmd)
            for cmd in self.COMMAND_PATTERN.findall(transcript)
            if cmd.strip()
        ]
        repeated_commands = Counter(commands)
        hot_commands = [(cmd, count) for cmd, count in repeated_commands.items() if count >= 3]

        if not hot_tools and not hot_commands:
            return None

        tokens = (
            sum((count - 1) * 320 for _, count in hot_tools)
            + sum((count - 1) * 220 for _, count in hot_commands)
        )
        severity = "high" if tokens >= 2_000 else "medium"

        evidence: list[str] = []
        for name, count in sorted(hot_tools, key=lambda item: item[1], reverse=True)[:3]:
            evidence.append(f"Tool `{name}` invoked {count}x")
        for cmd, count in sorted(hot_commands, key=lambda item: item[1], reverse=True)[:2]:
            short = cmd if len(cmd) <= 60 else f"{cmd[:57]}..."
            evidence.append(f"Command `{short}` repeated {count}x")

        return Finding(
            "repetitive_tool_calls",
            severity,
            tokens,
            "Batch related tool work and avoid re-running identical calls unless inputs changed.",
            evidence,
        )

    def detect_large_pastes(self, transcript: str) -> Finding | None:
        user_turns = re.findall(r'"role":\s*"user"[^}]*"content":\s*"([^"]{1500,})"', transcript)
        if not user_turns:
            return None
        total = sum(len(t) for t in user_turns)
        return Finding(
            "large_user_pastes",
            "critical",
            total // 4,
            "Move spec content to CLAUDE.md. Use #filename refs instead of pasting.",
            [f"{len(user_turns)} large paste(s) detected"],
        )

    def detect_opus_overuse(self, transcript: str) -> Finding | None:
        if "claude-opus" not in transcript:
            return None
        if "claude-sonnet" in transcript:
            return None  # hybrid session — check for mid-session switch separately
        turns = transcript.count('"role": "assistant"')
        return Finding(
            "opus_overuse",
            "high",
            turns * 800,
            "Switch to Sonnet for implementation: ce run uses Sonnet by default.",
            ["Entire session on Opus — Sonnet handles implementation equally well"],
        )

    def detect_no_compact(self, transcript: str) -> Finding | None:
        if "/compact" in transcript:
            return None
        turns = transcript.count('"role":')
        if turns < 45:  # was 20 — long sessions are the real problem
            return None
        return Finding(
            "no_compact_usage",
            "medium",
            turns * 120,
            "Use /clear + fresh session at natural breakpoints. "
            "ce run monitors context at 45% threshold.",
            [f"{turns} turns with no /compact or /clear"],
        )

    def detect_narration(self, transcript: str) -> Finding | None:
        phrases = [
            "let me first check",
            "now i will",
            "i'll start by",
            "let me look at",
            "first, let me",
            "i need to check",
        ]
        count = sum(transcript.lower().count(p) for p in phrases)
        if count < 3:
            return None
        return Finding(
            "claude_narration",
            "low",
            count * 80,
            'Add to CLAUDE.md: "Code only. No narration before or between edits."',
            [f"{count} narration phrases found"],
        )

    def detect_cache_invalidation(self, transcript: str) -> Finding | None:
        """
        Detects patterns that silently destroy prompt cache value:
        1. Mid-session model switch (Opus → Sonnet or vice versa)
        2. Signs of MCP server toggling mid-session
        """
        evidence: list[str] = []
        tokens_lost = 0

        models_found = re.findall(r"claude-(opus|sonnet|haiku)-[\d.-]+", transcript)
        if len(set(models_found)) > 1:
            evidence.append(
                f"Multiple models detected in session: {set(models_found)}. "
                "Each model switch invalidates the entire prompt cache prefix."
            )
            turns = transcript.count('"role":')
            tokens_lost += turns * 400  # rough: re-caching cost per remaining turn

        if re.search(r"threshold_pct\s*=\s*[6-9]\d", transcript):
            evidence.append(
                "Compact threshold >60% detected in config — "
                "context quality is already degraded by the time it fires."
            )

        if not evidence:
            return None

        return Finding(
            "cache_invalidation",
            "critical",
            tokens_lost,
            "Keep entire session on one model (model_router sets it once at start). "
            "Never switch models mid-session. Set threshold_pct = 45 in defaults.toml.",
            evidence,
        )

    def _normalize_signature(self, value: str) -> str:
        normalized = " ".join(value.lower().split())
        return normalized[:120]

    def _estimate_tokens(self, transcript: str) -> tuple[int, int | None, int | None]:
        estimated_total = transcript.count('"role":') * 1_500

        input_tokens = [int(x) for x in re.findall(r'"input_tokens"\s*:\s*(\d+)', transcript)]
        output_tokens = [int(x) for x in re.findall(r'"output_tokens"\s*:\s*(\d+)', transcript)]
        cache_tokens = [
            int(x)
            for x in re.findall(r'"cache_read_input_tokens"\s*:\s*(\d+)', transcript)
        ]

        if not input_tokens and not output_tokens and not cache_tokens:
            return estimated_total, None, None

        total_input = sum(input_tokens)
        total_output = sum(output_tokens)
        total_cache = sum(cache_tokens)
        billed = max(total_input - total_cache, 0) + total_output
        return billed, billed, total_cache

    def run(self, transcript_path: Path) -> WasteReport:
        text = transcript_path.read_text(errors="replace")
        findings: list[Finding] = []

        for detect in [
            self.detect_cache_invalidation,  # most severe — check first
            self.detect_large_pastes,
            self.detect_repetitive_tool_calls,
            self.detect_opus_overuse,
            self.detect_file_reads,
            self.detect_bash_retries,
            self.detect_no_compact,
            self.detect_narration,
        ]:
            finding = detect(text)
            if finding:
                findings.append(finding)

        findings.sort(key=lambda finding: finding.tokens_wasted, reverse=True)
        total, billed, cached = self._estimate_tokens(text)
        waste = min(sum(finding.tokens_wasted for finding in findings), total) if total else 0
        return WasteReport(
            findings=findings,
            total_tokens=total,
            waste_tokens=waste,
            billed_tokens=billed,
            cache_read_tokens=cached,
        )
