from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .models import Document, Issue


DEFAULT_CONFIG = {
    "required_types": [
        "reservation_form",
        "payment_record",
        "transport_invoice",
        "seat_class_proof",
    ],
    "one_of_required_groups": [["ticket_purchase_request", "special_approval_form"]],
    "invoice_header": "电子科技大学长三角研究院（衢州）",
    "invoice_tax_no": "12330800MB1D854661",
    "low_confidence_threshold": 0.65,
    "max_medium_for_auto_pass": 0,
}


def run_rules(documents: list[Document]) -> tuple[list[Issue], dict[str, object]]:
    issues: list[Issue] = []
    computed: dict[str, object] = {}
    config = load_rule_config()
    required_types = set(config["required_types"])
    one_of_required_groups = config["one_of_required_groups"]
    header_text = config["invoice_header"]
    tax_no = config["invoice_tax_no"]
    low_confidence_threshold = float(config["low_confidence_threshold"])

    grouped = group_by_type(documents)
    for required in sorted(required_types):
        if not grouped.get(required):
            issues.append(
                Issue(
                    rule_id=f"R-COMPLETE-{required}",
                    severity="high",
                    message=f"缺少必需材料: {required}",
                    evidence="materials",
                )
            )

    for group in one_of_required_groups:
        if not any(grouped.get(item) for item in group):
            group_name = " 或 ".join(group)
            issues.append(
                Issue(
                    rule_id="R-COMPLETE-GROUP",
                    severity="high",
                    message=f"缺少分组必需材料: {group_name}",
                    evidence="materials",
                )
            )

    for doc in documents:
        if doc.confidence < low_confidence_threshold:
            issues.append(
                Issue(
                    rule_id="R-LOW-CONFIDENCE",
                    severity="medium",
                    message="材料识别置信度低，建议人工复核",
                    evidence=doc.path.name,
                )
            )
        if doc.verify_status == "invalid":
            issues.append(
                Issue(
                    rule_id="R-FAKE-001",
                    severity="high",
                    message="联网查验失败：发票为假或已作废",
                    evidence=doc.path.name,
                )
            )
        if "发现重复报销票据" in str(doc.fraud_reasons):
            issues.append(
                Issue(
                    rule_id="R-DUPLICATE-001",
                    severity="high",
                    message="发现重复报销的票据",
                    evidence=doc.path.name,
                )
            )

    request_date = find_request_date(grouped.get("ticket_purchase_request", []))
    travel_date = find_travel_date(
        grouped.get("transport_invoice", []) + grouped.get("seat_class_proof", [])
    )
    computed["request_date"] = request_date.isoformat() if request_date else None
    computed["travel_date"] = travel_date.isoformat() if travel_date else None

    if request_date and travel_date and travel_date < request_date:
        has_backfill_reason = any(
            ("后补" in doc.raw_text and "原因" in doc.raw_text)
            for doc in grouped.get("ticket_purchase_request", [])
        )
        has_special_form = bool(grouped.get("special_approval_form"))
        if not has_backfill_reason and not has_special_form:
            issues.append(
                Issue(
                    rule_id="R-TIME-001",
                    severity="high",
                    message="出行早于购票申请且无后补说明/特殊事项审批表",
                    evidence="ticket_purchase_request + travel_docs",
                )
            )

    all_text = "\n".join(doc.raw_text for doc in documents)
    if "YS102102" not in all_text:
        issues.append(
            Issue(
                rule_id="R-FIELD-001",
                severity="medium",
                message="未识别到报销项目号 YS102102",
                evidence="reservation_form",
            )
        )
    if "转卡" not in all_text:
        issues.append(
            Issue(
                rule_id="R-FIELD-002",
                severity="medium",
                message="未识别到支付方式 转卡",
                evidence="reservation_form",
            )
        )

    ticket_amount = sum(
        float(doc.fields.get("amount", 0) or 0)
        for doc in grouped.get("transport_invoice", [])
    )
    paid_amount = sum(
        float(doc.fields.get("paid_amount", 0) or 0)
        for doc in grouped.get("payment_record", [])
    )
    if not ticket_amount:
        ticket_amount = extract_amount(all_text, ["票面金额", "发票金额"]) or 0.0
    if not paid_amount:
        paid_amount = extract_amount(all_text, ["实付金额", "实际实付金额", "实际支付金额"]) or 0.0

    computed["ticket_amount"] = ticket_amount
    computed["paid_amount"] = paid_amount
    if ticket_amount > 0 and paid_amount > 0 and abs(ticket_amount - paid_amount) > 0.01:
        computed["reimbursable_amount"] = round(min(ticket_amount, paid_amount), 2)
        if "差异原因" not in all_text:
            issues.append(
                Issue(
                    rule_id="R-AMOUNT-001",
                    severity="high",
                    message="票面金额与实付金额不一致且未说明差异原因",
                    evidence="payment_record",
                )
            )

    invoice_text = "\n".join(doc.raw_text for doc in grouped.get("transport_invoice", []))
    if any(keyword in invoice_text for keyword in ["电子发票", "电子行程单", "电子客票"]):
        if header_text not in invoice_text:
            issues.append(
                Issue(
                    rule_id="R-INVOICE-001",
                    severity="high",
                    message="电子票据未识别到单位抬头",
                    evidence="transport_invoice",
                )
            )
        if tax_no not in invoice_text:
            issues.append(
                Issue(
                    rule_id="R-INVOICE-002",
                    severity="high",
                    message="电子票据未识别到纳税识别号",
                    evidence="transport_invoice",
                )
            )
        verification_docs = grouped.get("verification_report", [])
        if not verification_docs and "验证报告" not in all_text:
            issues.append(
                Issue(
                    rule_id="R-INVOICE-003",
                    severity="medium",
                    message="电子票据未识别到验证报告",
                    evidence="transport_invoice",
                )
            )
        elif verification_docs:
            ver_text = "\n".join(d.raw_text for d in verification_docs)
            for inv_doc in grouped.get("transport_invoice", []):
                inv_num = inv_doc.fields.get("invoice_number") or inv_doc.fields.get("ticket_number")
                if inv_num and inv_num not in ver_text:
                    issues.append(
                        Issue(
                            rule_id="R-INVOICE-003",
                            severity="high",
                            message=f"验证报告中未找到该发票记录 (票号: {inv_num})",
                            evidence=inv_doc.path.name,
                        )
                    )
        if "承诺首次报销不重复报销" not in all_text:
            issues.append(
                Issue(
                    rule_id="R-INVOICE-004",
                    severity="medium",
                    message="未识别到首次报销不重复报销承诺",
                    evidence="transport_invoice",
                )
            )

    return issues, computed


def load_rule_config() -> dict[str, object]:
    root_path = Path(__file__).resolve().parents[2]
    cfg_path = root_path / "config" / "rules_config.json"
    if not cfg_path.exists():
        return DEFAULT_CONFIG
    try:
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_CONFIG
    result = dict(DEFAULT_CONFIG)
    result.update(payload)
    return result


def group_by_type(documents: list[Document]) -> dict[str, list[Document]]:
    grouped: dict[str, list[Document]] = {}
    for doc in documents:
        grouped.setdefault(doc.doc_type, []).append(doc)
    return grouped


def extract_dates(text: str) -> list[date]:
    patterns = [
        r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?",
    ]
    values: list[date] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            y, m, d = match.groups()
            try:
                values.append(date(int(y), int(m), int(d)))
            except ValueError:
                continue
    return sorted(values)


def find_request_date(docs: list[Document]) -> date | None:
    all_dates: list[date] = []
    for doc in docs:
        all_dates.extend(extract_dates(doc.raw_text))
    return min(all_dates) if all_dates else None


def find_travel_date(docs: list[Document]) -> date | None:
    all_dates: list[date] = []
    for doc in docs:
        all_dates.extend(extract_dates(doc.raw_text))
    return min(all_dates) if all_dates else None


def extract_amount(text: str, keys: list[str]) -> float | None:
    for key in keys:
        regex = rf"{re.escape(key)}\s*[为:：]?\s*(\d+(?:\.\d{{1,2}})?)"
        match = re.search(regex, text)
        if match:
            return float(match.group(1))
    return None
