from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    category: str
    severity: str          # "low" | "medium" | "high" | "critical"
    tokens_wasted: int
    fix: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class WasteReport:
    findings: list[Finding]
    total_tokens: int
    waste_tokens: int

    @property
    def waste_pct(self) -> float:
        return self.waste_tokens / self.total_tokens if self.total_tokens else 0.0


class WasteDetector:

    def detect_file_reads(self, transcript: str) -> Finding | None:
        reads = len(re.findall(r"(Read \d+ file|let me (check|look at|read))", transcript, re.I))
        if reads < 3:
            return None
        return Finding(
            "unnecessary_file_reads", "high", reads * 600,
            "Add codebase map to CLAUDE.md — Claude won't need to navigate.",
            [f"{reads} file-read operations detected"],
        )

    def detect_bash_retries(self, transcript: str) -> Finding | None:
        retries = len(re.findall(
            r"(ModuleNotFoundError|No module named|Exit code 1.*retry)", transcript
        ))
        if retries < 2:
            return None
        return Finding(
            "bash_retry_loops", "medium", retries * 400,
            "Add run/test commands to CLAUDE.md.",
            [f"{retries} failed bash attempts"],
        )

    def detect_large_pastes(self, transcript: str) -> Finding | None:
        user_turns = re.findall(
            r'"role":\s*"user"[^}]*"content":\s*"([^"]{1500,})"', transcript
        )
        if not user_turns:
            return None
        total = sum(len(t) for t in user_turns)
        return Finding(
            "large_user_pastes", "critical", total // 4,
            "Move spec content to CLAUDE.md. Use #filename refs instead of pasting.",
            [f"{len(user_turns)} large paste(s) detected"],
        )

    def detect_opus_overuse(self, transcript: str) -> Finding | None:
        if "claude-opus" not in transcript:
            return None
        if "claude-sonnet" in transcript:
            return None   # hybrid session — check for mid-session switch separately
        turns = transcript.count('"role": "assistant"')
        return Finding(
            "opus_overuse", "high", turns * 800,
            "Switch to Sonnet for implementation: ce run uses Sonnet by default.",
            ["Entire session on Opus — Sonnet handles implementation equally well"],
        )

    def detect_no_compact(self, transcript: str) -> Finding | None:
        if "/compact" in transcript:
            return None
        turns = transcript.count('"role":')
        if turns < 45:     # was 20 — long sessions are the real problem
            return None
        return Finding(
            "no_compact_usage", "medium", turns * 120,
            "Use /clear + fresh session at natural breakpoints. "
            "ce run monitors context at 45% threshold.",
            [f"{turns} turns with no /compact or /clear"],
        )

    def detect_narration(self, transcript: str) -> Finding | None:
        phrases = [
            "let me first check", "now i will", "i'll start by",
            "let me look at", "first, let me", "i need to check",
        ]
        count = sum(transcript.lower().count(p) for p in phrases)
        if count < 3:
            return None
        return Finding(
            "claude_narration", "low", count * 80,
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

        # Mid-session model switch
        models_found = re.findall(r"claude-(opus|sonnet|haiku)-[\d.-]+", transcript)
        if len(set(models_found)) > 1:
            evidence.append(
                f"Multiple models detected in session: {set(models_found)}. "
                "Each model switch invalidates the entire prompt cache prefix."
            )
            turns = transcript.count('"role":')
            tokens_lost += turns * 400   # rough: re-caching cost per remaining turn

        # Old compact threshold in config (60% instead of 45%)
        if re.search(r"threshold_pct\s*=\s*[6-9]\d", transcript):
            evidence.append(
                "Compact threshold >60% detected in config — "
                "context quality is already degraded by the time it fires."
            )

        if not evidence:
            return None

        return Finding(
            "cache_invalidation", "critical", tokens_lost,
            "Keep entire session on one model (model_router sets it once at start). "
            "Never switch models mid-session. Set threshold_pct = 45 in defaults.toml.",
            evidence,
        )

    def run(self, transcript_path: Path) -> WasteReport:
        text = transcript_path.read_text(errors="replace")
        findings: list[Finding] = []

        for detect in [
            self.detect_cache_invalidation,   # most severe — check first
            self.detect_large_pastes,
            self.detect_opus_overuse,
            self.detect_file_reads,
            self.detect_bash_retries,
            self.detect_no_compact,
            self.detect_narration,
        ]:
            f = detect(text)
            if f:
                findings.append(f)

        findings.sort(key=lambda f: f.tokens_wasted, reverse=True)
        total = text.count('"role":') * 1_500   # rough estimate
        waste = sum(f.tokens_wasted for f in findings)
        return WasteReport(findings, total, waste)
