"""Transparent heuristic scoring for Smart Scan findings.

Every score is the sum of explained components. We never present a bare number
as proof of steganography — each finding carries the reasons that produced its
score so the analyst can judge it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.util import printable_ratio, shannon_entropy, find_interesting


@dataclass
class Finding:
    title: str
    method: str
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    file_id: str | None = None      # stored recovered payload, if any

    def add(self, points: float, reason: str) -> None:
        self.score += points
        self.reasons.append(f"+{points:g}: {reason}")

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "method": self.method,
            "score": round(self.score, 2),
            "reasons": self.reasons,
            "details": self.details,
            "file_id": self.file_id,
        }


# Known signature names that strongly imply a real embedded file.
_STRONG_SIGS = {"ZIP", "PNG", "JPEG", "GIF", "PDF", "RAR", "7Z", "ELF", "PE",
                "GZIP", "BZIP2", "XZ", "SQLITE", "CLASS", "PCAP"}


def score_payload(finding: Finding, data: bytes) -> Finding:
    """Score a recovered byte payload by its content."""
    from ..extraction import signatures

    if not data:
        finding.add(-5, "empty payload")
        return finding

    # File signatures at offset 0 are the strongest signal.
    sigs = signatures.scan(data, max_results=20)
    for s in sigs:
        if s["offset"] == 0 and s["name"] in _STRONG_SIGS:
            finding.add(40, f"valid {s['name']} file signature at offset 0")
            break
    else:
        for s in sigs:
            if s["name"] in _STRONG_SIGS and s["offset"] < 64:
                finding.add(20, f"{s['name']} signature near start (offset {s['offset']})")
                break

    # Readable text.
    pr = printable_ratio(data[:4096])
    if pr > 0.95:
        finding.add(25, f"payload is {pr*100:.0f}% printable text")
    elif pr > 0.75:
        finding.add(12, f"payload is {pr*100:.0f}% printable text")

    # Flag-like tokens / URLs.
    interesting = find_interesting(data)
    if interesting["flags"]:
        finding.add(50, f"flag-like token(s): {interesting['flags'][:3]}")
        finding.details["flags"] = interesting["flags"][:10]
    if interesting["urls"]:
        finding.add(10, f"URL(s) present: {interesting['urls'][:2]}")
    if interesting["base64"]:
        finding.add(8, "decodable base64 blob(s) present")

    # Entropy cues: a payload that is neither pure noise nor trivially flat.
    ent = shannon_entropy(data[:8192])
    finding.details["entropy"] = round(ent, 3)
    if ent < 1.0:
        finding.add(-3, f"very low entropy ({ent:.2f}) — likely padding/zeros")
    elif 2.0 < ent < 7.0:
        finding.add(5, f"structured entropy ({ent:.2f})")

    return finding


def rank(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: f.score, reverse=True)
