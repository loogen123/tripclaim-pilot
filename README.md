# TripClaim Pilot

自动化交通报销材料审核工具，支持批量读取报销资料并输出审批结论、问题清单与复核线索。

## 功能概览
- 材料扫描与识别：`pdf/ofd/docx/txt/jpg/png/webp/bmp`
- 文档分类：预约报销单、支付凭证、交通电子票据、舱位行程凭证等
- 规则校验：材料完整性、时间逻辑、金额逻辑与票据字段核对
- 防伪能力：重复票据检测、二维码交叉校验（扫码成功时）
- 审批输出：通过 / 转人工 / 驳回
- 诊断日志：文件级失败原因、候选类型、全局问题

## 项目结构
- `src/tripclaim/api.py`：FastAPI 接口与 Web 挂载
- `src/tripclaim/web/`：前端页面
- `src/tripclaim/engine.py`：审核主流程
- `src/tripclaim/parsers.py`：各类型文件文本提取与 OCR
- `src/tripclaim/classifier.py`：材料分类
- `src/tripclaim/rules.py`：规则引擎
- `src/tripclaim/verification.py`：防伪与查验逻辑

## 本地启动
```bash
python -m uvicorn tripclaim.api:app --host 127.0.0.1 --port 8766
```

访问：
- `http://127.0.0.1:8766/ui/`

## 输入与输出
- 输入：一个报销材料目录（可混合格式）
- 输出：
  - 审批结论
  - 全局问题（如缺失材料）
  - 问题文件明细（状态、原因、诊断）
  - 文件审核日志（`logs/case_xxx_file_audit.log`）

## 注意事项
- 若 OCR 依赖异常，系统会走兜底策略并输出诊断信息。
- 建议使用清晰原图，避免二次压缩截图导致识别失败。
- 规则可通过 `config/rules_config.json` 调整阈值与必需材料。

