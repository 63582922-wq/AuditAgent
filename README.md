# FXPG — 会计风险评估 Agent（产品级）

面向会计/财务实务的 **风险评估工作流 Agent**：上传资料 → 自动解析 → 规则引擎 → 跨文件比对 → 人工复核 → 生成交付物。

## 核心能力

- **54 条内置规则**（费用/发票/银行/合同/税务/工资社保/科目余额）
- **实体抽取 + Record Linking**（发票号/金额/主体关联）
- **跨文件比对**（合同↔发票↔流水三方匹配）
- **跨期风险 / IQR 异常检测**
- **持久化任务队列**（进度条、失败重试信息）
- **7 类交付物**（PDF 报告、Excel 清单、批注文件、补充资料清单等）
- **API Key 鉴权**、上传校验、审计日志
- **长期记忆 RAG**（按风险类别检索口径，供 LLM 分析）

## 快速启动

### 本地开发（SQLite）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./fxpg.db
uvicorn app.main:app --reload --port 8000

# 新终端
cd frontend && npm install && npm run dev
```

### 生产部署（Docker + PostgreSQL）

```bash
export API_KEY=your-secret-key
chmod +x scripts/start-prod.sh
./scripts/start-prod.sh
```

或：

```bash
docker compose up -d --build
```

- 前端：http://localhost:3000
- 后端：http://localhost:8000/docs
- 健康检查：`GET /health` → `version: 2.1.0`

## 完整测试流程

```bash
# 1. 生成/更新测试样例
python scripts/create_fixtures.py

# 2. 运行测试
cd backend && pytest tests/ -q

# 3. 界面测试
# 新建项目 → 上传 fixtures/ 下全部 5 个文件 → 开始分析
```

| 样例文件 | 验证点 |
|---------|--------|
| sample_expense.csv | 大额缺发票、跨期入账 |
| sample_invoice_list.csv | 重复发票、金额不一致 |
| sample_bank_statement.csv | 个人账户、超大额流水 |
| sample_contract.docx | 合同金额 vs 发票 |
| sample_trial_balance.xlsx | 科目余额 |

## 环境变量

| 变量 | 说明 |
|------|------|
| DATABASE_URL | SQLite 或 PostgreSQL 连接串 |
| API_KEY | 设置后所有 API 需 `X-API-Key` 头 |
| OPENAI_API_KEY | 可选，启用 LLM 风险分析解释 |
| ENABLE_LLM | 默认 true，无 key 时跳过 |
| MAX_UPLOAD_MB | 单文件上限，默认 50MB |

前端 `.env.local`：

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000/api
NEXT_PUBLIC_API_KEY=your-secret-key
```

## OCR（发票/扫描 PDF）

Docker 镜像已含 Tesseract。本地 macOS：

```bash
brew install tesseract tesseract-lang
pip install pytesseract
```

## 项目结构

```text
FXPG/
├── docker-compose.yml      # postgres + backend + frontend
├── backend/
│   ├── app/                # FastAPI + Agent 工作流
│   ├── rules/              # 54 条 JSON 规则
│   ├── alembic/            # 数据库迁移
│   └── tests/              # 单元 + 集成测试
├── frontend/               # Next.js 全页面
├── fixtures/               # 完整测试样例集
└── scripts/
    ├── create_fixtures.py
    └── start-prod.sh
```

## API  Highlights

| 接口 | 说明 |
|------|------|
| POST /api/projects/{id}/analyze | 启动分析任务 |
| GET /api/projects/{id}/jobs/latest | 查询进度 |
| POST /api/projects/{id}/regenerate-outputs | 复核后重新生成报告 |
| GET /api/projects/{id}/logs | 审计追踪 |
| POST /api/rules | 新增自定义规则 |
