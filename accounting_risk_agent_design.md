# 会计风险评估 Agent 系统设计说明

## 一、我要做的是什么

我要开发一个真正意义上的 **会计风险评估智能体 Agent**，不是简单的聊天机器人。

这个 Agent 面向个人工作提效使用。用户上传 Excel、Word、PDF、图片等会计、财务、税务、合同、票据、银行流水资料后，Agent 能够自动识别资料类型，拆解分析任务，调用不同工具读取文件内容，结合会计风险规则引擎、业务规则引擎、搜索能力和长期记忆，对资料进行风险评估、批注更正，并最终生成可交付成果。

最终交付物包括：

```text
1. 风险评估摘要
2. PDF 风险报告
3. Excel 风险清单
4. 原始 Excel 批注文件
5. 图片 / PDF 标注结果
6. 补充资料清单
7. 更正建议清单
```

这个系统的核心目标不是“让 AI 看一看资料”，而是实现：

```text
上传资料
→ 自动理解资料
→ 自动拆解任务
→ 自动调用工具
→ 自动结构化提取
→ 自动执行风险规则
→ 自动交叉比对
→ 自动生成风险判断
→ 自动输出交付物
```

---

## 二、这个 Agent 必须具备的能力

真正的 Agent 至少需要以下能力：

```text
1. 大脑：LLM 推理模型
2. 视觉能力：图片 / 扫描 PDF / 发票 / 合同截图识别
3. 文件解析能力：Excel、Word、PDF、图片
4. 任务规划能力：自动拆解任务
5. 短期记忆：保存当前项目分析状态
6. 长期记忆：保存用户规则、历史案例、报告偏好
7. 工具调用能力：自动选择并调用工具
8. 规则引擎能力：执行会计、税务、票据、合同、数据一致性规则
9. 检索能力：搜索政策、规则、历史案例
10. 产物生成能力：生成 PDF、Excel、批注图片
11. 人工复核机制：标记不确定风险
12. 审计追踪能力：每个风险点都能追溯依据
```

---

## 三、系统整体架构

建议采用以下架构：

```text
前端上传界面
    ↓
任务创建层
    ↓
Agent Runtime / 智能体运行时
    ↓
Planner 任务规划器
    ↓
文件识别与解析层
    ├── Excel Parser
    ├── Word Parser
    ├── PDF Parser
    ├── OCR Engine
    ├── Vision Model
    └── Table Extractor
    ↓
结构化数据层
    ↓
短期记忆 / 项目状态库
    ↓
规则引擎层
    ├── 会计核算规则
    ├── 税务风险规则
    ├── 发票票据规则
    ├── 合同风险规则
    ├── 银行流水规则
    ├── 报表勾稽规则
    └── 数据一致性规则
    ↓
LLM 分析解释层
    ↓
长期记忆 / 知识库 / RAG
    ↓
风险结果库
    ↓
交付物生成层
    ├── PDF 报告
    ├── Excel 风险清单
    ├── 原 Excel 批注
    ├── 图片批注
    └── PDF 批注
```

---

## 四、推荐技术架构

### 1. 前端

建议使用：

```text
Next.js / React
```

前端需要提供：

```text
1. 文件上传
2. 项目列表
3. 分析进度展示
4. 风险结果预览
5. 人工复核界面
6. 报告下载
7. Excel / PDF / 图片结果下载
```

前端页面建议包括：

```text
/                         首页
/projects                 项目列表
/projects/[id]            项目详情
/projects/[id]/files      文件资料
/projects/[id]/risks      风险清单
/projects/[id]/review     人工复核
/projects/[id]/outputs    交付物下载
/settings/rules           规则库管理
/settings/memory          长期记忆管理
```

### 2. 后端

建议使用：

```text
Python FastAPI
```

后端职责：

```text
1. 接收上传文件
2. 创建分析任务
3. 调用 Agent Runtime
4. 调用文件解析工具
5. 执行规则引擎
6. 保存项目状态
7. 生成报告
8. 提供 API 给前端调用
```

### 3. Agent 编排

建议使用：

```text
LangGraph / 自研状态机
```

不要一开始用完全自由的 Agent。你的 Agent 应该是：

```text
固定主流程 + 局部动态决策
```

也就是说，主流程由系统控制：

```text
上传 → 分类 → 解析 → 抽取 → 规则 → 比对 → 报告
```

但每一步内部可以让模型判断：

```text
这个文件属于哪类？
这个 PDF 是文本型还是扫描型？
这个风险是否需要人工复核？
这些文件之间应该如何交叉比对？
```

### 4. 数据库

建议使用：

```text
PostgreSQL
```

用于保存：

```text
1. 用户项目
2. 文件记录
3. 解析结果
4. 风险结果
5. 规则库
6. 任务状态
7. 报告记录
8. 人工复核记录
```

### 5. 向量库 / 长期记忆

建议使用：

```text
pgvector
```

直接和 PostgreSQL 放在一起，第一版不用单独上复杂向量数据库。

长期记忆包括：

```text
1. 用户偏好
2. 报告模板
3. 风险判断口径
4. 历史项目案例
5. 会计税务知识片段
6. 自定义规则说明
```

### 6. 文件存储

本地开发可以使用：

```text
本地文件系统
```

正式使用建议：

```text
S3 / MinIO / 阿里云 OSS / 腾讯云 COS
```

保存：

```text
1. 原始文件
2. 解析后的中间文件
3. 生成的报告
4. 批注后的 Excel / PDF / 图片
```

---

## 五、核心模块设计

### 模块 1：任务创建模块

用户上传资料后，系统创建一个项目任务。

项目结构：

```json
{
  "project_id": "case_2026_001",
  "project_name": "某公司2025年度会计风险评估",
  "status": "created",
  "uploaded_files": [],
  "created_at": "2026-06-04T10:00:00"
}
```

任务状态包括：

```text
created              已创建
uploaded             文件已上传
classifying          正在分类
parsing              正在解析
extracting           正在抽取
running_rules        正在执行规则
cross_checking       正在交叉比对
generating_report    正在生成报告
needs_review         需要人工复核
completed            已完成
failed               失败
```

### 模块 2：文件识别模块

Agent 上传文件后，先判断文件类型。

文件类型包括：

```text
.xlsx / .xls       Excel
.docx / .doc       Word
.pdf               PDF
.jpg / .png        图片
.csv               CSV
.zip               批量资料包
```

然后进一步判断资料类别。

资料类别包括：

```text
financial_statement       财务报表
trial_balance             科目余额表
expense_detail            费用明细
invoice_list              发票清单
invoice_image             发票图片
bank_statement            银行流水
contract                  合同协议
tax_return                税务申报表
payroll                   工资表
social_security           社保公积金
fixed_asset               固定资产
accounts_receivable       应收账款
accounts_payable          应付账款
audit_workpaper           审计底稿
business_description      业务说明
unknown                   未知资料
```

输出结构：

```json
{
  "file_id": "file_001",
  "file_name": "费用明细.xlsx",
  "file_ext": ".xlsx",
  "file_type": "excel",
  "document_category": "expense_detail",
  "confidence": 0.92,
  "needs_manual_confirm": false
}
```

分类逻辑：

```text
1. 根据文件扩展名初步判断文件类型
2. 根据文件名关键词判断资料类别
3. 根据文件内容表头 / 标题 / 关键词二次判断
4. 如果置信度低于阈值，标记为人工确认
```

例如：

```text
文件名包含“费用”“明细”“报销” → expense_detail
文件名包含“银行”“流水”“对账单” → bank_statement
文件名包含“合同”“协议” → contract
文件名包含“发票”“进项”“销项” → invoice_list / invoice_image
表头包含“借方”“贷方”“科目编码” → trial_balance
表头包含“发票号码”“税额”“价税合计” → invoice_list
```

### 模块 3：Excel 解析模块

Excel 是第一优先级。

需要解析：

```text
1. sheet 名称
2. 表头
3. 单元格值
4. 公式
5. 合并单元格
6. 批注
7. 单元格格式
8. 隐藏行列
9. 金额列
10. 日期列
11. 科目列
12. 摘要列
```

技术可用：

```text
openpyxl
pandas
```

但注意：

```text
pandas 适合读表格数据
openpyxl 适合保留格式、批注、颜色、单元格位置
```

所以建议两者结合：

```text
pandas 负责数据分析
openpyxl 负责原文件批注和格式操作
```

Excel 解析输出：

```json
{
  "file_id": "file_001",
  "sheets": [
    {
      "sheet_name": "费用明细",
      "header_row": 1,
      "columns": [
        {
          "name": "日期",
          "type": "date",
          "column_letter": "A"
        },
        {
          "name": "摘要",
          "type": "text",
          "column_letter": "B"
        },
        {
          "name": "金额",
          "type": "amount",
          "column_letter": "C"
        }
      ],
      "rows": [
        {
          "row_number": 2,
          "values": {
            "日期": "2025-01-03",
            "摘要": "咨询服务费",
            "金额": 128000,
            "发票号": ""
          }
        }
      ]
    }
  ]
}
```

### 模块 4：PDF 解析模块

PDF 分两类：

```text
1. 文本型 PDF
2. 扫描型 PDF
```

判断逻辑：

```text
如果 PDF 中可以提取到足够文本 → 文本型 PDF
如果提取文本为空或很少 → 扫描型 PDF
```

文本型 PDF 处理：

```text
PDF
→ 提取文本
→ 提取表格
→ 保留页码
→ 保留文本块坐标
→ 输出结构化内容
```

扫描型 PDF 处理：

```text
PDF
→ 每页转图片
→ OCR
→ 版面分析
→ 字段抽取
→ 输出结构化内容
```

可用工具：

```text
PyMuPDF
pdfplumber
pytesseract / PaddleOCR / 云 OCR
```

PDF 输出结构：

```json
{
  "file_id": "file_002",
  "file_type": "pdf",
  "pdf_type": "scanned",
  "pages": [
    {
      "page_number": 1,
      "text": "合同编号...",
      "blocks": [
        {
          "text": "合同金额：500,000元",
          "bbox": [120, 300, 420, 330]
        }
      ]
    }
  ]
}
```

### 模块 5：图片识别模块

图片包括：

```text
发票截图
合同照片
凭证图片
银行回单
报销单据
业务单据
```

图片识别不能只靠文本模型。

需要：

```text
OCR + 视觉模型 + 规则校验
```

处理流程：

```text
图片
→ 图像预处理
→ OCR 文字识别
→ 版面区域识别
→ 字段抽取
→ 置信度校验
→ 转结构化数据
```

图像预处理包括：

```text
1. 旋转矫正
2. 去噪
3. 灰度化
4. 对比度增强
5. 裁剪边缘
6. 表格线检测
```

发票图片需要抽取：

```text
发票代码
发票号码
开票日期
购买方名称
购买方税号
销售方名称
销售方税号
项目名称
金额
税率
税额
价税合计
备注
```

输出：

```json
{
  "document_type": "invoice_image",
  "fields": {
    "invoice_number": "12345678",
    "invoice_date": "2025-03-12",
    "buyer_name": "A公司",
    "seller_name": "B公司",
    "amount_without_tax": 100000,
    "tax_rate": "6%",
    "tax_amount": 6000,
    "total_amount": 106000
  },
  "confidence": {
    "invoice_number": 0.98,
    "total_amount": 0.96,
    "tax_rate": 0.88
  }
}
```

### 模块 6：Word 解析模块

Word 主要用于合同、说明、审计底稿。

需要解析：

```text
1. 标题
2. 正文
3. 表格
4. 页眉页脚
5. 批注
6. 修订痕迹
7. 段落结构
```

合同类 Word 重点抽取：

```text
合同编号
合同主体
签订日期
合同金额
付款节点
服务内容
税率
发票类型
收款账户
履约期限
违约条款
签章情况
```

输出：

```json
{
  "document_type": "contract",
  "fields": {
    "contract_no": "HT-2025-001",
    "party_a": "A公司",
    "party_b": "B公司",
    "contract_amount": 500000,
    "tax_rate": "6%",
    "invoice_type": "增值税专用发票",
    "payment_terms": [
      {
        "condition": "合同签订后",
        "ratio": "50%",
        "amount": 250000
      }
    ]
  }
}
```

---

## 六、Agent 工作流设计

### 主流程

```text
Step 1：接收用户上传资料
Step 2：创建项目任务
Step 3：识别文件类型
Step 4：判断资料类别
Step 5：选择解析工具
Step 6：解析文件内容
Step 7：结构化抽取关键字段
Step 8：建立项目数据索引
Step 9：Planner 拆解风险评估任务
Step 10：执行单文件规则检查
Step 11：执行跨文件一致性检查
Step 12：执行政策 / 知识库检索
Step 13：生成风险点
Step 14：风险分级
Step 15：生成更正建议
Step 16：标记人工复核项
Step 17：生成 Excel 风险清单
Step 18：生成 PDF 风险报告
Step 19：生成批注文件
Step 20：输出交付资料
```

### Agent Planner 逻辑

Planner 的输入：

```json
{
  "project_id": "case_001",
  "files": [
    {
      "file_id": "file_001",
      "document_category": "expense_detail"
    },
    {
      "file_id": "file_002",
      "document_category": "contract"
    },
    {
      "file_id": "file_003",
      "document_category": "invoice_list"
    }
  ]
}
```

Planner 输出：

```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "task_type": "parse_expense_detail",
      "tool": "excel_parser",
      "input_file": "file_001"
    },
    {
      "task_id": "task_002",
      "task_type": "extract_contract_fields",
      "tool": "pdf_parser",
      "input_file": "file_002"
    },
    {
      "task_id": "task_003",
      "task_type": "check_invoice_completeness",
      "tool": "rule_engine",
      "depends_on": ["task_001", "task_002"]
    },
    {
      "task_id": "task_004",
      "task_type": "cross_check_contract_invoice_amount",
      "tool": "cross_checker",
      "depends_on": ["task_001", "task_002", "task_003"]
    }
  ]
}
```

Planner 的原则：

```text
1. 先解析，再判断
2. 先单文件风险，再跨文件风险
3. 先规则判断，再大模型解释
4. 对金额、日期、重复项使用程序计算，不靠模型猜
5. 对模糊业务场景使用 LLM 辅助判断
6. 置信度低的结果进入人工复核
```

---

## 七、短期记忆设计

短期记忆是当前项目的工作状态。

建议存储为数据库中的 project_state，也可以运行时保存在 Redis。

结构：

```json
{
  "project_id": "case_001",
  "current_step": "running_rules",
  "uploaded_files": [
    "file_001",
    "file_002"
  ],
  "parsed_documents": [
    "doc_001",
    "doc_002"
  ],
  "extracted_entities": {
    "companies": ["A公司", "B公司"],
    "amounts": [128000, 500000],
    "dates": ["2025-01-03", "2025-03-12"]
  },
  "risks": [
    "risk_001",
    "risk_002"
  ],
  "pending_review": [
    "risk_003"
  ],
  "generated_outputs": []
}
```

短期记忆用于：

```text
1. 断点续跑
2. 防止重复分析
3. 跟踪当前任务进度
4. 保存中间结果
5. 支持人工复核后继续生成报告
```

---

## 八、长期记忆设计

长期记忆不是简单聊天记录，而是系统知识和用户偏好。

分为 5 类：

### 1. 用户偏好记忆

```json
{
  "memory_type": "user_preference",
  "content": "用户偏好报告简洁、实务导向，高风险问题优先展示。",
  "tags": ["report_style", "risk_order"]
}
```

### 2. 风险判断口径

```json
{
  "memory_type": "risk_policy",
  "content": "咨询服务费金额超过10000元时，原则上需要合同、发票、付款记录三方匹配。",
  "tags": ["expense", "consulting_fee", "high_risk"]
}
```

### 3. 报告模板记忆

```json
{
  "memory_type": "report_template",
  "content": "PDF 报告应包含：项目概况、资料清单、风险汇总、主要问题、详细风险清单、整改建议、补充资料清单。",
  "tags": ["pdf_report"]
}
```

### 4. 历史案例记忆

```json
{
  "memory_type": "case_example",
  "content": "某项目中，个人账户收取客户款项被判定为高风险，建议补充代收说明并调整账务处理。",
  "tags": ["bank_statement", "personal_account", "high_risk"]
}
```

### 5. 专业知识记忆

```json
{
  "memory_type": "accounting_knowledge",
  "content": "费用税前扣除通常需要真实、合法、有效的凭证作为支持。",
  "tags": ["tax", "expense_deduction"]
}
```

长期记忆检索逻辑：

```text
当 Agent 分析某个风险点时：
1. 根据风险类别生成检索 query
2. 从长期记忆 / 知识库中检索相关规则、案例、模板
3. 将检索结果作为上下文提供给 LLM
4. 生成更贴合用户口径的风险解释和建议
```

---

## 九、规则引擎设计

规则引擎是这个系统最核心的部分。

不要把规则全部写在 Prompt 里。

规则应该独立存储为 JSON / YAML / 数据库记录。

### 规则结构

```json
{
  "rule_id": "EXP-001",
  "rule_name": "大额费用缺少发票",
  "risk_category": "税务风险",
  "risk_level": "高",
  "applicable_document_type": "expense_detail",
  "condition": {
    "all": [
      {
        "field": "amount",
        "operator": ">=",
        "value": 10000
      },
      {
        "field": "invoice_number",
        "operator": "is_empty"
      }
    ]
  },
  "evidence_fields": [
    "date",
    "summary",
    "supplier",
    "amount",
    "invoice_number"
  ],
  "suggestion_template": "该笔费用金额较大，但未发现对应发票。建议补充发票、合同及付款凭证，否则可能存在税前扣除风险。",
  "manual_review_required": true
}
```

### 规则类型

#### 1. 单文件规则

针对一个文件内部检查。

例如：

```text
费用明细中金额为空
费用明细中发票号为空
银行流水中摘要异常
发票清单中税率异常
合同中未约定发票类型
```

#### 2. 跨文件规则

多个文件之间比对。

例如：

```text
合同金额 ≠ 发票金额
合同主体 ≠ 发票销售方
合同付款节点 ≠ 银行流水付款时间
费用明细金额 ≠ 发票价税合计
银行流水收款方 ≠ 合同主体
税表收入 ≠ 利润表收入
```

#### 3. 勾稽关系规则

财务报表内部或表间关系检查。

例如：

```text
资产负债表未分配利润期末数 ≠ 期初数 + 净利润 - 分配利润
利润表收入 ≠ 增值税申报销售额
现金流量表经营现金流与银行流水大额差异
科目余额表借贷不平
应收账款账龄异常
应付账款长期挂账
```

#### 4. 异常检测规则

适合用算法辅助。

例如：

```text
金额异常大
同一供应商频繁小额拆分
短时间内重复报销
整数金额过多
费用集中在月末
摘要高度相似
供应商名称异常相似
```

---

## 十、算法设计

### 算法 1：文件分类算法

综合使用：

```text
文件名关键词
文件扩展名
表头关键词
正文关键词
LLM 分类
置信度评分
```

伪代码：

```python
def classify_document(file):
    score = {}

    score += classify_by_extension(file.ext)
    score += classify_by_filename(file.name)
    score += classify_by_headers(file.headers)
    score += classify_by_content_keywords(file.text)

    if max(score.values()) < 0.65:
        llm_result = llm_classify(file.summary)
        score[llm_result.category] += llm_result.confidence

    category = max(score, key=score.get)

    return {
        "category": category,
        "confidence": score[category],
        "needs_manual_confirm": score[category] < 0.75
    }
```

### 算法 2：表头识别算法

Excel 不一定第一行就是表头。

需要自动识别表头行。

逻辑：

```text
1. 扫描前 20 行
2. 统计每行非空单元格数量
3. 判断关键词命中数量
4. 判断下一行是否像数据
5. 得分最高的行作为表头
```

表头关键词：

```text
日期
摘要
科目
供应商
客户
金额
税额
价税合计
发票号
合同号
借方
贷方
余额
银行账号
对方户名
```

伪代码：

```python
def detect_header_row(sheet):
    candidates = []

    for row in first_20_rows(sheet):
        non_empty_count = count_non_empty(row)
        keyword_score = count_header_keywords(row)
        next_row_data_score = evaluate_next_row_as_data(row)

        total_score = (
            non_empty_count * 0.2 +
            keyword_score * 0.6 +
            next_row_data_score * 0.2
        )

        candidates.append((row.index, total_score))

    return max(candidates, key=lambda x: x[1])[0]
```

### 算法 3：字段标准化算法

不同表可能使用不同列名。

例如：

```text
金额
价税合计
报销金额
付款金额
发生额
借方金额
贷方金额
```

要统一映射为标准字段：

```json
{
  "amount": ["金额", "报销金额", "付款金额", "价税合计", "发生额"],
  "date": ["日期", "发生日期", "开票日期", "付款日期", "记账日期"],
  "supplier": ["供应商", "销售方", "收款方", "对方户名"],
  "customer": ["客户", "购买方", "付款方"],
  "invoice_number": ["发票号", "发票号码", "票号"],
  "summary": ["摘要", "用途", "备注", "项目名称"]
}
```

字段标准化输出：

```json
{
  "original_column": "价税合计",
  "standard_field": "amount",
  "confidence": 0.96
}
```

### 算法 4：金额一致性比对算法

用于合同、发票、流水、费用明细之间比对。

逻辑：

```text
1. 提取所有金额字段
2. 按主体、日期、合同号、发票号、摘要建立关联
3. 设置容差阈值
4. 判断是否一致
```

容差规则：

```text
完全一致：差额 = 0
小额尾差：差额 <= 1 元
合理差异：差额 / 基准金额 <= 0.5%
异常差异：超过容差
```

输出：

```json
{
  "risk_id": "AMT-001",
  "risk_category": "数据一致性风险",
  "risk_level": "中",
  "problem": "合同金额与发票累计金额不一致",
  "evidence": {
    "contract_amount": 500000,
    "invoice_total": 460000,
    "difference": 40000
  },
  "suggestion": "请核实是否存在未开票金额、合同变更或发票缺失。"
}
```

### 算法 5：主体一致性比对算法

用于检查：

```text
合同主体
发票购买方 / 销售方
银行流水收付款方
费用明细供应商
```

需要处理名称不完全一致的问题。

例如：

```text
北京某某科技有限公司
某某科技有限公司
北京某某科技公司
```

可以使用：

```text
字符串清洗
关键词提取
模糊匹配
编辑距离
统一社会信用代码优先匹配
LLM 辅助判断
```

主体标准化：

```text
去掉空格
去掉括号
统一全角半角
去掉“有限公司”“有限责任公司”等尾缀后辅助比较
优先使用税号 / 银行账号 / 统一社会信用代码
```

输出：

```json
{
  "entity_a": "北京某某科技有限公司",
  "entity_b": "某某科技有限公司",
  "match_score": 0.86,
  "match_result": "likely_same",
  "needs_manual_review": true
}
```

### 算法 6：重复发票检测算法

检测字段：

```text
发票代码
发票号码
开票日期
销售方
购买方
金额
税额
价税合计
```

规则：

```text
发票代码 + 发票号码完全相同 → 高风险重复
发票号码相同但金额不同 → 高风险
销售方 + 金额 + 日期相同但发票号不同 → 疑似重复
```

输出：

```json
{
  "risk_id": "INV-001",
  "risk_category": "票据风险",
  "risk_level": "高",
  "problem": "发现重复发票号码",
  "evidence": {
    "invoice_number": "12345678",
    "rows": [12, 45]
  },
  "suggestion": "请核实是否重复报销或重复入账。"
}
```

### 算法 7：跨期风险检测算法

比较：

```text
业务发生日期
发票日期
付款日期
入账日期
合同签订日期
```

规则示例：

```text
发票日期晚于入账日期太久 → 中风险
合同签订日期晚于业务发生日期 → 中 / 高风险
费用入账日期跨年度但业务发生在上一年度 → 跨期风险
收入确认日期与合同履约期间不一致 → 收入确认风险
```

输出：

```json
{
  "risk_category": "会计核算风险",
  "risk_level": "中",
  "problem": "费用可能存在跨期入账",
  "evidence": {
    "business_date": "2024-12-20",
    "booking_date": "2025-01-15",
    "amount": 32000
  },
  "suggestion": "请核实该费用归属期间，必要时调整至正确会计期间。"
}
```

### 算法 8：异常金额检测算法

对费用明细、银行流水做异常检测。

方法：

```text
1. 按科目分组
2. 按供应商分组
3. 计算均值、中位数、标准差、四分位数
4. 使用 IQR 或 Z-score 判断异常
```

IQR 规则：

```text
Q1 = 第一四分位数
Q3 = 第三四分位数
IQR = Q3 - Q1
异常上限 = Q3 + 1.5 * IQR
```

输出：

```json
{
  "risk_category": "异常交易风险",
  "risk_level": "中",
  "problem": "该笔费用金额显著高于同类费用水平",
  "evidence": {
    "amount": 128000,
    "category_median": 12000,
    "category_q3": 30000
  },
  "suggestion": "建议核查该笔费用的合同、发票、付款记录及业务真实性。"
}
```

### 算法 9：资料完整性检查算法

根据项目类型判断必须资料是否齐全。

例如会计风险评估需要：

```text
科目余额表
费用明细
收入明细
发票清单
银行流水
主要合同
税务申报表
工资社保资料
固定资产明细
往来明细
```

如果缺失，则生成补充资料清单：

```json
{
  "missing_documents": [
    {
      "document_type": "bank_statement",
      "importance": "高",
      "reason": "无法核对账面收付款与实际资金流水是否一致。"
    },
    {
      "document_type": "invoice_list",
      "importance": "高",
      "reason": "无法核查费用发票完整性及税务扣除风险。"
    }
  ]
}
```

---

## 十一、风险评分体系

每个风险点不要只写“高、中、低”，要有评分。

建议：

```text
风险等级 = 规则严重性 × 金额影响 × 证据充分性 × 发生概率 × 合规影响
```

评分字段：

```json
{
  "severity_score": 5,
  "amount_score": 4,
  "evidence_score": 3,
  "probability_score": 4,
  "compliance_score": 5,
  "total_score": 21,
  "risk_level": "高"
}
```

等级规则：

```text
0 - 7      低风险
8 - 15     中风险
16 - 25    高风险
```

金额影响评分：

```text
金额 < 1000              1 分
1000 - 10000             2 分
10000 - 50000            3 分
50000 - 100000           4 分
> 100000                 5 分
```

可根据实际业务调整。

---

## 十二、风险结果标准结构

每个风险点必须统一格式。

```json
{
  "risk_id": "RISK-0001",
  "project_id": "case_001",
  "risk_category": "税务风险",
  "risk_subcategory": "费用扣除凭证不足",
  "risk_level": "高",
  "risk_score": 21,
  "source_file_id": "file_001",
  "source_file_name": "费用明细.xlsx",
  "source_location": {
    "sheet": "费用明细",
    "row": 32,
    "column": "发票号"
  },
  "related_files": [
    "合同.pdf",
    "发票清单.xlsx"
  ],
  "problem": "该笔咨询服务费金额较大，但未发现对应发票号。",
  "evidence": {
    "date": "2025-03-12",
    "summary": "咨询服务费",
    "supplier": "B公司",
    "amount": 128000,
    "invoice_number": ""
  },
  "rule_triggered": "EXP-001 大额费用缺少发票",
  "analysis": "该笔费用金额较大，且摘要为咨询服务费，通常应具备合同、发票和付款记录作为支撑。目前资料中未发现发票信息，因此存在税前扣除凭证不足风险。",
  "suggestion": "建议补充对应发票、合同及付款凭证；如无法补充，应评估是否需要进行纳税调整。",
  "correction_action": "标记为需补充资料",
  "manual_review_required": true,
  "confidence": 0.86,
  "status": "pending"
}
```

---

## 十三、人工复核机制

必须有人机协同。

以下情况进入人工复核：

```text
1. OCR 置信度低
2. 文件分类置信度低
3. 主体模糊匹配
4. 金额差异接近阈值
5. 缺少关键资料
6. LLM 判断不确定
7. 规则冲突
8. 高风险事项
```

人工复核状态：

```text
pending          待复核
confirmed        已确认风险
dismissed        已排除
modified         已修改
needs_more_info  需要补充资料
```

人工复核后，系统要保存判断，作为长期记忆或规则优化依据。

---

## 十四、搜索 / RAG 逻辑

Agent 需要搜索能力，但不是每次都搜索。

触发搜索的情况：

```text
1. 涉及新政策、新税法、新监管口径
2. 规则库没有覆盖
3. 用户要求查政策依据
4. LLM 判断存在不确定
5. 风险建议需要引用外部依据
```

搜索结果不能直接作为结论，必须：

```text
搜索
→ 摘要
→ 提取相关规则
→ 与当前风险点匹配
→ 标记来源
→ 生成建议
```

RAG 检索内容：

```text
1. 内部规则库
2. 历史项目案例
3. 用户口径
4. 报告模板
5. 政策资料
6. 会计准则资料
```

---

## 十五、交付物生成

### 1. Excel 风险清单

字段：

```text
序号
风险等级
风险评分
风险类别
风险子类
文件名称
位置
问题描述
涉及金额
判断依据
触发规则
更正建议
是否需要人工复核
处理状态
备注
```

Excel 要求：

```text
1. 高风险行标红
2. 中风险行标黄
3. 低风险行标蓝 / 灰
4. 添加筛选
5. 冻结首行
6. 自动调整列宽
7. 可按风险等级排序
```

### 2. 原始 Excel 批注

在原始文件中：

```text
1. 异常单元格填充颜色
2. 添加批注
3. 新增“风险等级”列
4. 新增“风险说明”列
5. 新增“处理建议”列
```

例如：

```text
第 32 行发票号为空：
批注：该笔费用金额 128,000 元，未发现发票号，建议补充发票及合同。
```

### 3. PDF 报告

报告结构：

```text
封面
一、项目基本信息
二、资料清单
三、整体风险结论
四、风险等级汇总
五、主要高风险事项
六、详细风险清单
七、资料缺失情况
八、更正建议
九、需人工复核事项
十、附件说明
```

PDF 风格：

```text
正式
简洁
偏实务
不要花哨
高风险突出展示
表格清晰
适合对外交付或内部留档
```

### 4. 图片 / PDF 批注

对于图片和扫描 PDF：

```text
1. 根据 OCR bbox 坐标定位异常区域
2. 在异常位置画框
3. 添加旁注文本
4. 导出新图片或带批注 PDF
```

示例：

```text
发票金额处红框：
“该发票金额 106,000 元，与费用明细 128,000 元不一致。”
```

---

## 十六、工具调用设计

Agent 可用工具列表：

```python
tools = [
    "classify_file",
    "parse_excel",
    "parse_word",
    "parse_pdf",
    "ocr_image",
    "extract_table",
    "extract_entities",
    "normalize_fields",
    "run_rule_engine",
    "cross_check_documents",
    "search_policy",
    "retrieve_memory",
    "calculate_risk_score",
    "generate_excel_report",
    "annotate_excel",
    "generate_pdf_report",
    "annotate_image",
    "save_project_state"
]
```

工具调用原则：

```text
1. 文件类型明确时直接调用对应解析器
2. 文件内容不确定时先分类
3. PDF 先判断文本型还是扫描型
4. 图片必须走 OCR / 视觉识别
5. 金额计算必须走程序，不靠模型
6. 风险判断先走规则引擎，再由 LLM 解释
7. 政策不确定时调用搜索
8. 生成报告前必须等待人工复核或标记未复核
```

---

## 十七、数据库表设计

### projects

```sql
id
name
status
created_at
updated_at
```

### files

```sql
id
project_id
file_name
file_type
document_category
storage_path
parse_status
confidence
created_at
```

### parsed_documents

```sql
id
project_id
file_id
document_type
content_json
text_content
created_at
```

### extracted_entities

```sql
id
project_id
file_id
entity_type
entity_value
standard_value
source_location
confidence
created_at
```

### rules

```sql
id
rule_id
rule_name
risk_category
risk_level
applicable_document_type
condition_json
suggestion_template
enabled
created_at
updated_at
```

### risks

```sql
id
project_id
risk_id
risk_category
risk_level
risk_score
source_file_id
source_location_json
problem
evidence_json
rule_triggered
analysis
suggestion
manual_review_required
confidence
status
created_at
updated_at
```

### review_records

```sql
id
project_id
risk_id
review_status
review_comment
reviewed_at
```

### memories

```sql
id
memory_type
content
embedding
tags
created_at
updated_at
```

### outputs

```sql
id
project_id
output_type
file_name
storage_path
created_at
```

---

## 十八、MVP 第一版范围

第一版不要做太大。

建议 MVP 只做：

```text
1. Excel 上传
2. PDF 上传
3. 基础图片 OCR
4. 文件自动分类
5. Excel 表头识别
6. 字段标准化
7. 基础规则引擎
8. 单文件风险识别
9. 简单跨文件金额比对
10. 风险清单生成
11. Excel 导出
12. PDF 报告导出
```

第一版暂时不做：

```text
1. 多 Agent 协作
2. 复杂长期自学习
3. 财务软件直连
4. 全自动政策引用
5. 高级图片批注
6. 复杂审计底稿自动生成
```

---

## 十九、MVP 推荐开发顺序

### 阶段 1：基础框架

```text
1. 搭建前端上传页面
2. 搭建 FastAPI 后端
3. 建立 PostgreSQL 数据库
4. 实现项目创建
5. 实现文件上传和存储
```

### 阶段 2：文件解析

```text
1. 实现 Excel parser
2. 实现 PDF parser
3. 实现图片 OCR 接口
4. 实现文件分类
5. 实现结构化结果保存
```

### 阶段 3：规则引擎

```text
1. 设计规则 JSON 格式
2. 实现规则执行器
3. 实现金额、日期、主体等基础判断
4. 生成风险结果
```

### 阶段 4：Agent Planner

```text
1. 根据文件类别生成任务计划
2. 按任务依赖顺序执行工具
3. 保存项目状态
4. 支持失败重试
```

### 阶段 5：报告生成

```text
1. 生成风险 Excel
2. 生成 PDF 报告
3. 原始 Excel 添加批注
4. 输出下载链接
```

### 阶段 6：人工复核

```text
1. 风险列表页面
2. 修改风险状态
3. 添加复核意见
4. 复核后重新生成报告
```

---

## 二十、给 Codex 的完整开发描述

```md
我要开发一个真正意义的会计风险评估 Agent，不是普通聊天机器人。

系统目标：
用户上传 Excel、Word、PDF、图片等会计、财务、税务、合同、票据、银行流水资料后，Agent 自动识别资料类型，自动拆解任务，自动调用文件解析、OCR、规则引擎、搜索、记忆、报告生成等工具，对资料进行会计风险评估、批注更正，并生成交付物。

核心交付物：
1. 风险评估摘要
2. PDF 风险报告
3. Excel 风险清单
4. 原始 Excel 批注文件
5. 图片 / PDF 标注结果
6. 补充资料清单
7. 更正建议清单

系统架构：
前端使用 Next.js / React。
后端使用 Python FastAPI。
数据库使用 PostgreSQL。
长期记忆使用 PostgreSQL + pgvector。
文件存储使用本地存储，后期可切换到 S3 / OSS / MinIO。
Agent 编排使用 LangGraph 或自研状态机。
Excel 解析使用 openpyxl + pandas。
Word 解析使用 python-docx。
PDF 解析使用 PyMuPDF + pdfplumber。
图片识别使用 OCR + 多模态视觉模型。
报告生成使用 openpyxl、ReportLab / WeasyPrint。
图片批注使用 Pillow / OpenCV。

Agent 必须具备：
1. 大脑：LLM 推理模型
2. 文件解析能力：Excel、Word、PDF、图片
3. 视觉能力：OCR / Vision Model
4. Planner：任务规划器
5. 短期记忆：项目状态管理
6. 长期记忆：用户偏好、历史案例、规则知识库
7. 工具调用能力
8. 会计风险规则引擎
9. 跨文件比对能力
10. 人工复核机制
11. 交付物生成能力
12. 审计追踪能力

主流程：
1. 用户上传资料
2. 创建项目
3. 识别文件类型
4. 判断资料类别
5. 选择对应解析工具
6. 解析文件内容
7. 结构化抽取关键字段
8. 建立项目数据索引
9. Planner 拆解风险评估任务
10. 执行单文件规则检查
11. 执行跨文件一致性检查
12. 必要时调用搜索或知识库
13. 生成风险点
14. 计算风险评分
15. 生成更正建议
16. 标记人工复核项
17. 生成人工复核页面
18. 生成 Excel 风险清单
19. 生成 PDF 报告
20. 生成批注文件

文件分类：
系统需要根据文件扩展名、文件名、表头、正文关键词和 LLM 分类判断资料类别。
资料类别包括：
- financial_statement 财务报表
- trial_balance 科目余额表
- expense_detail 费用明细
- invoice_list 发票清单
- invoice_image 发票图片
- bank_statement 银行流水
- contract 合同协议
- tax_return 税务申报表
- payroll 工资表
- social_security 社保公积金
- fixed_asset 固定资产
- accounts_receivable 应收账款
- accounts_payable 应付账款
- audit_workpaper 审计底稿
- business_description 业务说明
- unknown 未知资料

Excel 解析要求：
1. 读取 sheet
2. 自动识别表头行
3. 提取表头、行数据、公式、批注、格式
4. 识别金额列、日期列、供应商列、摘要列、发票号列
5. 保留原始单元格位置，便于后续批注
6. 输出结构化 JSON

PDF 解析要求：
1. 判断 PDF 是文本型还是扫描型
2. 文本型 PDF 使用文本解析
3. 扫描型 PDF 转图片后走 OCR
4. 提取文本、表格、页码、坐标位置
5. 输出结构化 JSON

图片识别要求：
1. 使用 OCR / Vision Model
2. 支持发票、合同照片、凭证截图、银行回单
3. 提取关键字段
4. 保留 OCR 置信度和 bbox 坐标
5. 支持后续图片标注

规则引擎要求：
规则不能只写在 Prompt 中，必须独立为 JSON / YAML / 数据库规则。
每条规则包含：
- rule_id
- rule_name
- risk_category
- risk_level
- applicable_document_type
- condition
- evidence_fields
- suggestion_template
- manual_review_required

风险类型包括：
1. 会计核算风险
2. 税务风险
3. 票据风险
4. 合同风险
5. 银行流水风险
6. 数据一致性风险
7. 资料完整性风险
8. 异常交易风险

风险结果统一结构：
- risk_id
- project_id
- risk_category
- risk_subcategory
- risk_level
- risk_score
- source_file_id
- source_file_name
- source_location
- related_files
- problem
- evidence
- rule_triggered
- analysis
- suggestion
- correction_action
- manual_review_required
- confidence
- status

风险评分：
风险等级 = 规则严重性 + 金额影响 + 证据充分性 + 发生概率 + 合规影响。
0-7 为低风险，8-15 为中风险，16-25 为高风险。

人工复核：
以下情况必须进入人工复核：
1. OCR 置信度低
2. 文件分类置信度低
3. 主体模糊匹配
4. 金额差异接近阈值
5. 高风险事项
6. 规则冲突
7. 资料不足
8. LLM 判断不确定

输出要求：
Excel 风险清单字段：
- 序号
- 风险等级
- 风险评分
- 风险类别
- 风险子类
- 文件名称
- 位置
- 问题描述
- 涉及金额
- 判断依据
- 触发规则
- 更正建议
- 是否需要人工复核
- 处理状态
- 备注

PDF 报告结构：
1. 封面
2. 项目基本信息
3. 资料清单
4. 整体风险结论
5. 风险等级汇总
6. 主要高风险事项
7. 详细风险清单
8. 资料缺失情况
9. 更正建议
10. 需人工复核事项
11. 附件说明

MVP 第一版只需要优先实现：
1. 项目创建
2. 文件上传
3. Excel 解析
4. PDF 文本解析
5. 基础 OCR 接口预留
6. 文件分类
7. 字段标准化
8. 基础规则引擎
9. 单文件风险识别
10. 简单跨文件金额比对
11. 风险清单生成
12. Excel 导出
13. PDF 报告导出
14. 人工复核状态管理

第一版不要做成普通聊天机器人，而是做成可执行工作流 Agent：
上传资料 → 解析资料 → 结构化 → 规则判断 → 交叉比对 → 风险评估 → 人工复核 → 输出交付物。
```

---

## 二十一、最重要的实现原则

这个系统要想真的像 Agent，而不是普通 AI 工具，必须坚持这几条：

```text
1. 模型不直接处理所有事，模型负责判断和解释，工具负责执行。
2. Excel、PDF、图片必须先解析成结构化数据，再交给模型分析。
3. 金额、日期、重复项、勾稽关系必须用程序算法，不靠模型猜。
4. 风险判断必须有规则引擎，不能只靠 Prompt。
5. 每个风险点必须能追溯来源文件、页码、行号、单元格。
6. 高风险和低置信度事项必须进入人工复核。
7. 用户每次人工修改，都应该沉淀成长期记忆或规则优化。
8. 最终交付物必须是 PDF / Excel / 批注文件，而不是只在聊天窗口里回答。
```

---

## 一句话总结

这个 Agent 的本质是一个 **会计风险工作流执行系统**。

```text
LLM 是大脑；
OCR / 文件解析器是眼睛；
规则引擎是判断标准；
数据库和向量库是记忆；
工具调用系统是手脚；
报告生成器是交付能力。
```

