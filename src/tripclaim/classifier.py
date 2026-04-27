from __future__ import annotations

from pathlib import Path


DOC_TYPE_RULES: dict[str, list[str]] = {
    "process_guide": ["报销流程", "资料清单", "交通费报销流程", "提交审核"],
    "reservation_form": ["预约报销单", "网上预约报销", "申请报销单", "打印确认单"],
    "ticket_purchase_request": ["交通票购票申请", "购票申请", "校园数字管理云平台"],
    "payment_record": ["支付记录", "实付金额", "票面金额", "差异原因"],
    "special_approval_form": ["特殊事项审批表", "后补原因", "分管领导"],
    "transport_invoice": ["电子行程单", "航空运输电子客票行程单", "火车票", "大巴车票", "发票"],
    "seat_class_proof": ["经济舱", "舱位", "电子登机牌", "订单截图"],
    "cash_explain_form": ["现金支出说明书", "现金支出说明", "现金支出情况说明书"],
    "verification_report": ["验证报告", "电子票据查验", "发票查验", "查验平台"],
}


def classify_document(path: Path, text: str) -> tuple[str, float]:
    filename = path.name.lower()
    if "预约报销单" in filename:
        return "reservation_form", 0.95
    if "支付记录" in filename:
        return "payment_record", 0.95
    if "特殊事项审批表" in filename:
        return "special_approval_form", 0.95
    if "查验平台" in filename:
        return "verification_report", 0.95
    if "电子行程单" in filename:
        return "transport_invoice", 0.95
    if "经济舱" in filename:
        return "seat_class_proof", 0.95
    if "现金支出" in filename:
        return "cash_explain_form", 0.95

    if "报销流程" in text and "资料清单" in text:
        return "process_guide", 0.99
    hit_scores: dict[str, int] = {}
    for doc_type, keywords in DOC_TYPE_RULES.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += 2
            if kw.lower() in filename:
                score += 1
        if score > 0:
            hit_scores[doc_type] = score
    if not hit_scores:
        return "unknown", 0.0
    best_type = max(hit_scores, key=hit_scores.get)
    best_score = hit_scores[best_type]
    confidence = min(0.99, 0.5 + best_score * 0.08)
    return best_type, confidence
