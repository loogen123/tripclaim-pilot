from __future__ import annotations

from pathlib import Path

from .classifier import classify_document
from .models import AuditResult, Document, Issue
from .parsers import extract_text, scan_files
from .rules import load_rule_config, run_rules
from .verification import process_fraud_detection


def audit_folder(folder: Path) -> AuditResult:
    files = scan_files(folder)
    documents: list[Document] = []
    for file_path in files:
        raw_text = extract_text(file_path)
        doc_type, confidence = classify_document(file_path, raw_text)
        documents.append(
            Document(
                path=file_path,
                extension=file_path.suffix.lower(),
                raw_text=raw_text,
                doc_type=doc_type,
                confidence=confidence,
                fields={},
            )
        )

    process_fraud_detection(documents)

    issues, computed_values = run_rules(documents)

    cfg = load_rule_config()
    high_count = sum(1 for i in issues if i.severity == "high")
    medium_count = sum(1 for i in issues if i.severity == "medium")
    max_medium_for_auto_pass = int(cfg.get("max_medium_for_auto_pass", 0))
    decision = "通过"
    if high_count > 0:
        decision = "驳回"
    elif medium_count > max_medium_for_auto_pass:
        decision = "转人工"

    stats = {
        "total_files": len(files),
        "detected_types": sorted(list({d.doc_type for d in documents})),
        "high_issues": high_count,
        "medium_issues": medium_count,
    }
    detected_documents = [
        {
            "file": str(doc.path),
            "type": doc.doc_type,
            "confidence": round(doc.confidence, 2),
        }
        for doc in documents
    ]
    file_checks = build_file_checks(documents, issues, float(cfg.get("low_confidence_threshold", 0.65)))
    fraud_score_total = sum(doc.fraud_score for doc in documents)
    return AuditResult(
        decision=decision,
        issues=issues,
        stats=stats,
        detected_documents=detected_documents,
        file_checks=file_checks,
        computed_values=computed_values,
        fraud_score_total=fraud_score_total,
    )


def build_file_checks(
    documents: list[Document], issues: list[Issue], low_confidence_threshold: float
) -> list[dict]:
    result: list[dict] = []
    for doc in documents:
        matched = []
        for issue in issues:
            evidence = issue.evidence
            if evidence == doc.path.name or evidence in str(doc.path):
                matched.append(issue)
                continue
            if evidence == doc.doc_type:
                matched.append(issue)
                continue
        has_high = any(item.severity == "high" for item in matched)
        has_medium = any(item.severity == "medium" for item in matched)
        status = "合规"
        reasons: list[str] = []
        if doc.doc_type == "unknown":
            status = "待复核"
            reasons.append("材料类型未识别")
        if doc.confidence < low_confidence_threshold:
            status = "待复核"
            reasons.append("识别置信度偏低")
        if has_medium:
            status = "待复核"
            reasons.extend(item.message for item in matched if item.severity == "medium")
        if has_high:
            status = "不合规"
            reasons = [item.message for item in matched if item.severity == "high"]
        if doc.fraud_score >= 70:
            status = "不合规"
            reasons.extend(doc.fraud_reasons)
        elif doc.fraud_score > 0:
            status = "待复核"
            reasons.extend(doc.fraud_reasons)

        result.append(
            {
                "file": str(doc.path),
                "type": doc.doc_type,
                "confidence": round(doc.confidence, 2),
                "fraud_score": doc.fraud_score,
                "status": status,
                "reasons": "；".join(dict.fromkeys(reasons)) if reasons else "",
            }
        )
    return result
