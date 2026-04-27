# Tasks

- [x] Task 1: 建立审批输入与文件接入能力
  - [x] SubTask 1.1: 定义报销批次输入结构与文件清单元数据
  - [x] SubTask 1.2: 实现文件夹扫描与格式校验（pdf/doc/docx/jpg/png/jpeg）
  - [x] SubTask 1.3: 生成批次级输入清单供后续解析使用

- [x] Task 2: 实现多格式文档解析与材料分类
  - [x] SubTask 2.1: 接入 PDF/Word 文本提取与图片 OCR
  - [x] SubTask 2.2: 建立材料类型识别规则（预约单、购票申请、支付记录等）
  - [x] SubTask 2.3: 输出统一字段模型与识别置信度

- [x] Task 3: 实现合规规则引擎
  - [x] SubTask 3.1: 实现完整性校验规则
  - [x] SubTask 3.2: 实现时序校验规则（含后补与特殊事项条件）
  - [x] SubTask 3.3: 实现金额与票据校验规则（抬头、税号、验证报告）

- [x] Task 4: 实现审批决策与结果导出
  - [x] SubTask 4.1: 实现通过/驳回/转人工决策逻辑
  - [x] SubTask 4.2: 生成不合规项清单（规则编号、原因、证据定位）
  - [x] SubTask 4.3: 导出 `result.json` 与 `result.md`

- [x] Task 5: 完成验收验证
  - [x] SubTask 5.1: 使用真实样例文件夹跑通端到端流程
  - [x] SubTask 5.2: 校验结果与流程单规则一致
  - [x] SubTask 5.3: 修正验收中发现的规则误判

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 2
- Task 4 depends on Task 3
- Task 5 depends on Task 4

# 执行计划
- 第 1-2 天：完成 Task 1，能稳定接入报销文件夹
- 第 3-5 天：完成 Task 2，跑通 PDF/Word/OCR 解析与材料分类
- 第 6-8 天：完成 Task 3，落地四类合规规则
- 第 9-10 天：完成 Task 4，输出审批结论与报告
- 第 11-12 天：完成 Task 5，做真实样例验收与修正
