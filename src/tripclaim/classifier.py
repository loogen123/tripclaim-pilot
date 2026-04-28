from __future__ import annotations

from pathlib import Path


DOC_TYPE_RULES: dict[str, list[str]] = {
    "process_guide": ["报销流程", "资料清单", "交通费报销流程", "提交审核"],
    "reservation_form": ["预约报销单", "网上预约报销", "申请报销单", "打印确认单"],
    "ticket_purchase_request": ["交通票购票申请", "购票申请", "校园数字管理云平台"],
    "payment_record": ["支付记录", "实付金额", "票面金额", "差异原因", "账单详情", "交易成功", "支付成功", "微信支付", "支付宝", "商户单号", "交易单号", "付款时间", "付款凭证"],
    "special_approval_form": ["特殊事项审批表", "后补原因", "分管领导"],
    "transport_invoice": ["电子行程单", "航空运输电子客票行程单", "火车票", "大巴车票", "发票", "数电票", "全电发票"],
    "seat_class_proof": ["经济舱", "舱位", "电子登机牌", "订单截图", "二等座", "一等座", "商务座", "公务舱", "头等舱", "硬座", "软卧", "硬卧", "高铁", "动车", "航班号", "起飞", "降落", "乘车人"],
    "cash_explain_form": ["现金支出说明书", "现金支出说明", "现金支出情况说明书"],
    "verification_report": ["验证报告", "电子票据查验", "发票查验", "查验平台"],
}


def classify_document(path: Path, text: str) -> tuple[str, float]:
    doc_type, confidence, _ = classify_document_with_debug(path, text)
    return doc_type, confidence


def classify_document_with_debug(path: Path, text: str) -> tuple[str, float, dict[str, object]]:
    filename = path.name.lower()
    if "预约报销单" in filename:
        return "reservation_form", 0.95, {"match_mode": "filename_exact", "matched_keyword": "预约报销单", "raw_text_len": len(text)}
    if "支付记录" in filename:
        return "payment_record", 0.95, {"match_mode": "filename_exact", "matched_keyword": "支付记录", "raw_text_len": len(text)}
    if "特殊事项审批表" in filename:
        return "special_approval_form", 0.95, {"match_mode": "filename_exact", "matched_keyword": "特殊事项审批表", "raw_text_len": len(text)}
    if "电子行程单" in filename:
        return "transport_invoice", 0.95, {"match_mode": "filename_exact", "matched_keyword": "电子行程单", "raw_text_len": len(text)}
    if ("电子发票" in filename or "数电票" in filename or "全电发票" in filename) and "查验平台" not in filename:
        return "transport_invoice", 0.95, {"match_mode": "filename_exact", "matched_keyword": "电子发票", "raw_text_len": len(text)}
    if "查验平台" in filename and ("验证报告" in filename or "查验结果" in filename):
        return "verification_report", 0.95, {"match_mode": "filename_exact", "matched_keyword": "查验平台+验证报告", "raw_text_len": len(text)}
    if "经济舱" in filename:
        return "seat_class_proof", 0.95, {"match_mode": "filename_exact", "matched_keyword": "经济舱", "raw_text_len": len(text)}
    if "现金支出" in filename:
        return "cash_explain_form", 0.95, {"match_mode": "filename_exact", "matched_keyword": "现金支出", "raw_text_len": len(text)}

    if "报销流程" in text and "资料清单" in text:
        return "process_guide", 0.99, {"match_mode": "text_exact", "matched_keyword": "报销流程+资料清单", "raw_text_len": len(text)}
    hit_scores: dict[str, int] = {}
    hit_details: dict[str, list[str]] = {}
    for doc_type, keywords in DOC_TYPE_RULES.items():
        score = 0
        matched_keywords: list[str] = []
        for kw in keywords:
            if kw in text:
                score += 2
                matched_keywords.append(kw)
            if kw.lower() in filename:
                score += 1
                matched_keywords.append(f"filename:{kw}")
        if score > 0:
            hit_scores[doc_type] = score
            hit_details[doc_type] = matched_keywords
    if not hit_scores:
        debug = {
            "match_mode": "no_match",
            "raw_text_len": len(text),
            "hint": "未命中任何分类关键词",
        }
        return "unknown", 0.0, debug
    best_type = max(hit_scores, key=hit_scores.get)
    best_score = hit_scores[best_type]
    confidence = min(0.99, 0.5 + best_score * 0.08)
    top_candidates = sorted(hit_scores.items(), key=lambda item: item[1], reverse=True)[:3]
    debug = {
        "match_mode": "keyword_score",
        "raw_text_len": len(text),
        "top_candidates": [
            {"type": doc_type, "score": score, "matched_keywords": hit_details.get(doc_type, [])}
            for doc_type, score in top_candidates
        ],
    }
    return best_type, confidence, debug
