import json
import re
from pathlib import Path
from typing import Any
import datetime

from .models import Document

LOCAL_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "invoice_db.json"

def ensure_db() -> None:
    if not LOCAL_DB_PATH.parent.exists():
        LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOCAL_DB_PATH.exists():
        LOCAL_DB_PATH.write_text(json.dumps({"invoices": []}), encoding="utf-8")

def get_db() -> dict[str, Any]:
    ensure_db()
    try:
        return json.loads(LOCAL_DB_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"invoices": []}

def save_db(data: dict[str, Any]) -> None:
    LOCAL_DB_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def extract_qr_data(image_path: Path) -> dict[str, str]:
    """使用 pyzbar 从发票图片中提取二维码信息"""
    if not image_path.exists() or image_path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".bmp"]:
        return {}
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode
        img = Image.open(image_path)
        barcodes = decode(img)
        for barcode in barcodes:
            data = barcode.data.decode("utf-8")
            if data.startswith("01,"):
                fields = data.split(",")
                if len(fields) >= 7:
                    return {
                        "invoice_code": fields[2],
                        "invoice_number": fields[3],
                        "amount_pre_tax": fields[4],
                        "date": fields[5],
                        "check_code": fields[6]
                    }
    except Exception as e:
        pass
    return {}

def extract_invoice_fields(text: str) -> dict[str, str]:
    """使用正则从文本中提取发票号、发票代码、金额等信息"""
    fields: dict[str, str] = {}
    
    invoice_num_match = re.search(r"发票号码[:：]?\s*(\d{8,20})", text)
    if invoice_num_match:
        fields["invoice_number"] = invoice_num_match.group(1)
        
    invoice_code_match = re.search(r"发票代码[:：]?\s*(\d{10,12})", text)
    if invoice_code_match:
        fields["invoice_code"] = invoice_code_match.group(1)
        
    amount_match = re.search(r"(?:价税合计|小写|金额|总金额)[(（]?.*?[)）]?[:：￥¥]?\s*(\d+(?:\.\d{1,2})?)", text)
    if amount_match:
        fields["amount"] = amount_match.group(1)
        
    pre_tax_match = re.search(r"(?:不含税金额|金额|合计)[(（]?.*?[)）]?[:：￥¥]?\s*(\d+(?:\.\d{1,2})?)", text)
    if pre_tax_match:
        fields["amount_pre_tax"] = pre_tax_match.group(1)

    tax_match = re.search(r"(?:税额|税费)[(（]?.*?[)）]?[:：￥¥]?\s*(\d+(?:\.\d{1,2})?)", text)
    if tax_match:
        fields["tax_amount"] = tax_match.group(1)

    ticket_num_match = re.search(r"客票号[:：]?\s*(\d{3}-?\d{10})", text)
    if ticket_num_match:
        fields["ticket_number"] = ticket_num_match.group(1).replace("-", "")

    return fields

def check_duplicate(invoice_number: str) -> dict[str, str] | None:
    """检查本地库是否已存在该票号，如果存在则返回之前的报销信息"""
    if not invoice_number:
        return None
    db = get_db()
    invoices = db.get("invoices", {})
    if isinstance(invoices, list):  # 兼容老数据结构
        return {"timestamp": "未知"} if invoice_number in invoices else None
    return invoices.get(invoice_number)

def add_to_db(invoice_number: str, case_id: str = "unknown") -> None:
    """将新票号加入本地库"""
    if not invoice_number:
        return
    db = get_db()
    invoices = db.get("invoices", {})
    if isinstance(invoices, list):  # 自动迁移老数据
        new_invoices = {num: {"timestamp": "未知", "case_id": "unknown"} for num in invoices}
        invoices = new_invoices
    
    if invoice_number not in invoices:
        invoices[invoice_number] = {
            "timestamp": datetime.datetime.now().isoformat(),
            "case_id": case_id
        }
        db["invoices"] = invoices
        save_db(db)

def mock_online_verify(fields: dict[str, str]) -> dict[str, Any]:
    """Mock的联网查验服务"""
    invoice_number = fields.get("invoice_number") or fields.get("ticket_number")
    
    if not invoice_number:
        return {"status": "unchecked", "reason": "未提取到票号"}
        
    if invoice_number.endswith("999"):
        return {"status": "invalid", "reason": "发票查验失败：状态异常或不存在"}
        
    return {"status": "valid", "reason": "查验通过", "verified_amount": fields.get("amount")}

def process_fraud_detection(documents: list[Document]) -> None:
    """执行防伪检测管道"""
    for doc in documents:
        if doc.doc_type == "payment_record":
            paid_match = re.search(r"(?:实付金额|实际实付金额|实际支付金额)[:：￥¥]?\s*(\d+(?:\.\d{1,2})?)", doc.raw_text)
            if paid_match:
                doc.fields["paid_amount"] = float(paid_match.group(1))

        if doc.doc_type == "transport_invoice":
            extracted = extract_invoice_fields(doc.raw_text)
            doc.fields.update(extracted)
            
            # 发票内部逻辑交叉校验 (大写=小写=税额+金额)
            try:
                amt = float(extracted.get("amount", 0))
                pre_tax = float(extracted.get("amount_pre_tax", 0))
                tax = float(extracted.get("tax_amount", 0))
                if amt > 0 and pre_tax > 0 and tax > 0:
                    if abs((pre_tax + tax) - amt) > 0.05:
                        doc.fraud_score += 40
                        doc.fraud_reasons.append(f"发票金额逻辑异常: 不含税金额({pre_tax}) + 税额({tax}) ≠ 总金额({amt})")
            except ValueError:
                pass

            # 二维码校验防篡改与强制检测
            qr_data = extract_qr_data(doc.path)
            
            # 判断是否为电子票据（必须有二维码）
            is_electronic = any(kw in doc.raw_text for kw in ["电子发票", "电子客票", "电子行程单", "数电票"])
            
            if is_electronic and not qr_data:
                # 电子票据必须能扫出二维码，否则视为异常
                doc.fraud_score += 40
                doc.fraud_reasons.append("电子票据未识别到有效二维码，疑似截图不全或模糊篡改")
                
            if qr_data:
                qr_amt = qr_data.get("amount_pre_tax") or qr_data.get("amount")
                ocr_amt = extracted.get("amount_pre_tax") or extracted.get("amount")
                if qr_amt and ocr_amt and qr_amt != ocr_amt:
                    doc.fraud_score += 100
                    doc.fraud_reasons.append(f"发票被篡改: 二维码金额({qr_amt})与票面识别金额({ocr_amt})不一致")

            invoice_num = extracted.get("invoice_number") or extracted.get("ticket_number")
            if qr_data and qr_data.get("invoice_number"):
                invoice_num = qr_data.get("invoice_number")
            
            dup_info = check_duplicate(invoice_num)
            if invoice_num and dup_info:
                doc.fraud_score += 100
                doc.fraud_reasons.append(f"发现重复报销票据，票号: {invoice_num}，历史记录: {dup_info.get('case_id', '未知')}({dup_info.get('timestamp', '未知')})")
                continue 
            
            verify_res = mock_online_verify(extracted)
            doc.verify_status = verify_res["status"]
            if verify_res["status"] == "invalid":
                doc.fraud_score += 100
                doc.fraud_reasons.append(verify_res["reason"])
