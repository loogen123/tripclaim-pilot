# 票据防伪与校验机制 Specification (V1)

## 1. 目标范围
在现有的 `TripClaim` 审批流水线中，引入专门的“防造假与高可信度校验”机制。目标是识别并拦截潜在的票据造假风险，同时对核心票据（如全电发票、行程单）引入绝对可信的真伪判断依据，最终输出统一的 `fraud_score` 和判定结论，替代部分人工复核成本。

## 2. 核心架构设计

### 2.1 整体数据流向
现有的流水线在 `engine.py` 中的顺序为：
`文件扫描 -> 文本/图像识别(OCR) -> 文档分类(classifier.py) -> 规则校验(rules.py)`

**升级后的流水线设计：**
`文件扫描 -> 文本/图像识别(OCR) -> 文档分类 -> [新增] 结构化字段提取(Regex/AI) -> [新增] 数据增强与防伪核验 -> 规则校验(包含防伪拦截规则)`

### 2.2 防造假模块划分 (Fraud Detectors)
防伪机制采取分层过滤策略，按照**成本由低到高、可靠性由高到低**的顺序执行：

1. **强规则拦截层 (Level 1 - 最高优先级)**
   - **联网查验 (Online Verification)**：针对线上票据（全电发票、电子行程单），必须提取关键字段（票号、金额、日期等），调用国税局或航信接口进行联网查验。
   - **查验逻辑**：若接口返回“查无此票”、“已作废”或“金额不符”，直接判定为造假，阻断流程。

2. **图像与逻辑校验层 (Level 2 - 本地低成本检测)**
   - **重复票据检测 (Duplicate Detection)**：基于图像感知哈希 (`pHash`) 和关键字段（票号/金额/日期）的联合去重。历史库中命中即阻断。
   - **字段一致性校验 (Consistency Check)**：金额大小写一致性、含税/税额计算逻辑、日期与行程/城市的逻辑冲突校验。

3. **AI 辅助校验层 (Level 3 - 针对性视觉/语义检测)**
   - **篡改痕迹检测 (Tamper Detection)**：针对纸质票截图或无法联网查验的票据，利用专门的图像模型（如 ELA）或 VLM（如 GPT-4o）检测 PS、拼接、字体/排版异常。
   - **OCR 双通道交叉 (Dual-OCR Cross-check)**：对高风险票据，同时使用本地模型（如 PaddleOCR）和云端大模型进行识别，结果冲突即标记风险。

## 3. 关键数据结构变更

在 `models.py` 中，增强 `Document` 和 `AuditResult` 结构，以承载防伪信息。

```python
@dataclass
class Document:
    # ... 现有字段 ...
    fields: dict[str, Any] = field(default_factory=dict) # 用于存储提取的结构化字段（票号、金额等）
    fraud_score: int = 0  # 0-100 整数，越高越假
    fraud_reasons: list[str] = field(default_factory=list) # 具体的造假疑点说明
    verify_status: str = "unchecked" # 联网查验状态: unchecked, valid, invalid

@dataclass
class AuditResult:
    # ... 现有字段 ...
    fraud_score_total: int = 0
```

## 4. 决策策略配置化

在规则引擎前置判定 `fraud_score`，并在前端展示 `fraud_reasons` 以供财务复核。

- **`fraud_score >= 70` 或 `verify_status == "invalid"`**：自动拒绝 (High Issue)
- **`40 <= fraud_score < 70`**：强制转人工复核 (Medium Issue)
- **`< 40`**：进入常规合规性规则校验
