"""Triage model — clusters log lines into incidents and classifies them.

`FakeTriage` is deterministic and needs no API key: it groups by a normalized
signature and recognizes a couple of known error shapes. A real model reads the
content instead — implement `LLMTriage` (ESSENCE §6.1).
"""
import re
from dataclasses import dataclass, field


@dataclass
class Incident:
    slug: str
    severity: str   # noop | low | medium | high
    confidence: str  # low | medium | high
    root_cause: str
    summary: str
    affected_files: list = field(default_factory=list)
    sample_lines: list = field(default_factory=list)
    occurrences: int = 0


class FakeTriage:
    def cluster(self, lines: list[dict]) -> list[Incident]:
        errs = [l for l in lines if l.get("level") in ("WARN", "ERROR")]
        groups: dict[str, list[dict]] = {}
        for l in errs:
            groups.setdefault(self._signature(l["text"]), []).append(l)
        return [self._classify(ls) for ls in groups.values()]

    @staticmethod
    def _signature(text: str) -> str:
        return re.sub(r"\d+", "#", text)  # mask numbers so ids don't split a bug

    def _classify(self, ls: list[dict]) -> Incident:
        text = ls[0]["text"]
        samples = [l["text"] for l in ls[:3]]
        if "KeyError" in text and "price" in text:
            return Incident(
                slug="ingest-price-keyerror", severity="medium", confidence="high",
                root_cause="app/ingest.py assumes every record has a 'price' and drops the ones that don't",
                summary="Ingest drops records missing a 'price' field (logging an error for each)",
                affected_files=["app/ingest.py"], sample_lines=samples, occurrences=len(ls),
            )
        return Incident(
            slug="unclassified-error", severity="low", confidence="low",
            root_cause="unknown", summary=text[:80],
            affected_files=[], sample_lines=samples, occurrences=len(ls),
        )


class LLMTriage:
    """REAL triage adapter — IMPLEMENT ME (ESSENCE §6.1). Send the log lines to an
    LLM with forced structured output that returns incidents (slug, severity,
    confidence, root_cause, affected_files)."""

    def __init__(self, *, model: str, api_key: str) -> None:
        self.model, self.api_key = model, api_key

    def cluster(self, lines: list[dict]) -> list[Incident]:
        raise NotImplementedError("Wire your LLM here — ESSENCE.md §6.1.")
