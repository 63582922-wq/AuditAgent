# AuditAgent · 会议合规远程观察

面向罗氏 **SPCHECK / 远程观察** 场景的 Agent 工作流：导入 FX 观察案件 → 资料分类与解析 → Orchestrator 多 Agent → CMP 合规规则 → Remote Finding 生成 → 交付验收。

## 核心能力

- **Compliance Harness**：一键导入 `FX/` 案件文件夹，跑通完整观察链路
- **5 路子 Agent**：会议计划 / 签到与会 / 讲者核验 / 证据链 / 合规政策
- **CMP 合规规则**（讲课时长、证据缺失、签到一致性等）
- **Finding 交付物**（PDF / Excel）+ 前端交付验收
- **Orchestrator + Critic** 多 Agent 编排与质检
- **长期记忆 RAG**（合规口径与历史案例）

## 快速启动

```bash
# 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 LLM_API_KEY
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev
```

浏览器打开 http://localhost:3000 → **导入并运行 Harness**（默认指向 `./FX` 样本）。

### CLI 一键跑案件

```bash
python scripts/run_compliance_harness.py FX
```

## FX 样本案件

`FX/` 目录包含真实远程观察案例（A1P260307357 · 宝山学术交流），含：

- 观察元数据 Excel
- A1 会议导出、议程、签到、现场确认单
- 沟通短信、线上截图、演讲材料

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | DeepSeek 等文本 LLM（必填） |
| `VISION_API_KEY` | 智谱 GLM 视觉（图片/OCR，可选） |
| `AGENT_DOMAIN` | `compliance`（默认）或 `accounting` |
| `AGENT_EXECUTION_MODE` | `orchestrator`（默认） |
| `API_KEY` | 设置后 API 需 `X-API-Key` 头（**生产必填**） |
| `CORS_ORIGINS` | 前端公网地址，逗号分隔（生产必填） |
| `APP_ENV` | `development` / `production` |

前端 `frontend/.env.local`：

| 变量 | 说明 |
|------|------|
| `NEXT_PUBLIC_API_BASE` | 默认 `http://localhost:8000/api` |
| `NEXT_PUBLIC_DEFAULT_CASE_PATH` | Harness 默认案件目录 |

## 部署到 Render

详见 [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md)。仓库根目录含 `render.yaml` Blueprint：

1. Render → **New** → **Blueprint** → 连接 GitHub 仓库  
2. 部署向导中填写 `LLM_API_KEY`、`VISION_API_KEY`  
3. 首次部署后：API 服务设置 `CORS_ORIGINS`；Web 服务设置 `NEXT_PUBLIC_API_BASE=https://<api域名>/api`，并 **重新部署前端**

生产注意：`APP_ENV=production` 必须配置 `API_KEY`；用户上传存于持久盘 `/app/storage`。

## API 要点

| 端点 | 说明 |
|------|------|
| `POST /harness/run-case` | 导入 FX 目录并运行 Harness |
| `POST /projects/{id}/analyze` | 对已上传资料启动分析 |
| `POST /projects/{id}/deliverables/accept` | 验收交付物 |

## 测试

```bash
cd backend && pytest tests/test_compliance_harness.py -q
```
