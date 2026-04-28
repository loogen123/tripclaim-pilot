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

    type_names = {
        "process_guide": "报销流程指南",
        "reservation_form": "预约报销单",
        "ticket_purchase_request": "交通票购票申请",
        "payment_record": "支付记录凭证",
        "special_approval_form": "特殊事项审批表",
        "transport_invoice": "交通电子票据",
        "seat_class_proof": "舱位/行程凭证",
        "cash_explain_form": "现金支出说明书",
        "verification_report": "发票查验报告",
    }

    grouped = group_by_type(documents)
    for required in sorted(required_types):
        if not grouped.get(required):
            issues.append(
                Issue(
                    rule_id=f"R-COMPLETE-{required}",
                    severity="high",
                    message=f"缺少必需材料: {type_names.get(required, required)}",
                    evidence="materials",
                )
            )

    for group in one_of_required_groups:
        if not any(grouped.get(item) for item in group):
            group_name = " 或 ".join(type_names.get(item, item) for item in group)
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
    clean_text = "".join(all_text.split())  # 去除所有空格、换行符的纯净版文本
    
    reservation_text = "\n".join(doc.raw_text for doc in grouped.get("reservation_form", []))
    reservation_clean = "".join(reservation_text.split())
    # 仅在预约报销单文本有效时再做字段校验，避免OCR空文本导致误判
    if len(reservation_clean) >= 20:
        if not re.search(r"YS[1lI][0O]2[1lI][0O]2", reservation_clean, re.IGNORECASE):
            issues.append(
                Issue(
                    rule_id="R-FIELD-001",
                    severity="medium",
                    message="未识别到报销项目号 YS102102",
                    evidence="reservation_form",
                )
            )
        payment_method_patterns = [
            r"转卡",
            r"转账",
            r"银行卡",
            r"银行转账",
            r"对公转账",
            r"网银",
            r"微信支付",
            r"支付宝",
        ]
        if not any(re.search(pattern, reservation_clean, re.IGNORECASE) for pattern in payment_method_patterns):
            issues.append(
                Issue(
                    rule_id="R-FIELD-002",
                    severity="medium",
                    message="未识别到支付方式(转卡/转账/银行卡/微信支付/支付宝)",
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
