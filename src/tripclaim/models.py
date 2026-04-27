from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    path: Path
    extension: str
    raw_text: str
    doc_type: str = "unknown"
    confidence: float = 0.0
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Issue:
    rule_id: str
    severity: str
    message: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class AuditResult:
    decision: str
    issues: list[Issue]
    stats: dict[str, Any]
    detected_documents: list[dict[str, Any]]
    file_checks: list[dict[str, Any]]
    computed_values: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "issues": [item.to_dict() for item in self.issues],
            "stats": self.stats,
            "detected_documents": self.detected_documents,
            "file_checks": self.file_checks,
            "computed_values": self.computed_values,
        }
