# Render 部署指南

## 架构

| 服务 | 说明 |
|------|------|
| `fxpg-db` | PostgreSQL（Alembic 迁移 + 可选 pgvector） |
| `fxpg-api` | FastAPI 后端（Docker，含 Tesseract） |
| `fxpg-web` | Next.js 前端（Docker） |

## 一键 Blueprint

1. 将本仓库推送到 GitHub
2. [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint**
3. 连接仓库，Render 会读取根目录 `render.yaml`
4. 按提示补全 **Secret 环境变量**（见下表）
5. 部署完成后，在 **fxpg-api** 设置 `CORS_ORIGINS` 为前端公网地址
6. 在 **fxpg-web** 设置 `NEXT_PUBLIC_API_BASE` 为 `https://<api域名>/api`，**重新部署前端**（Next 构建时写入）

## 必配环境变量

### fxpg-api

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | DeepSeek 等文本模型 Key（必填） |
| `VISION_API_KEY` | 智谱 GLM-OCR Key（PDF/图片解析建议配置） |
| `API_KEY` | Blueprint 自动生成；前端 `NEXT_PUBLIC_API_KEY` 会同步 |
| `CORS_ORIGINS` | 例：`https://fxpg-web.onrender.com`（多个用逗号分隔） |
| `DATABASE_URL` | Blueprint 从数据库自动注入 |

可选：

| 变量 | 默认 | 说明 |
|------|------|------|
| `APP_ENV` | `production` | 生产模式 |
| `BOOTSTRAP_DATA_ON_STARTUP` | `true` | 种子规则/记忆 |
| `SYNC_PGVECTOR_ON_STARTUP` | `true` | 同步向量索引（需 PG 支持 vector 扩展） |
| `STORAGE_PATH` | `/app/storage` | 已挂载 1GB 持久盘 |

### fxpg-web

| 变量 | 说明 |
|------|------|
| `NEXT_PUBLIC_API_BASE` | `https://<你的-api-域名>/api` |
| `NEXT_PUBLIC_API_KEY` | 与后端 `API_KEY` 相同（Blueprint 可自动关联） |

## 健康检查

- 后端：`GET /health` → `{"status":"ok"}`
- 前端：打开首页，侧栏可切换中英文

## 本地与生产差异

| 项 | 本地 | Render |
|----|------|--------|
| 数据库 | SQLite（`.env`）或 docker-compose Postgres | 托管 Postgres |
| 上传文件 | `./backend/storage` | 持久盘 `/app/storage` |
| API 鉴权 | `API_KEY` 为空则开发模式放行 | **必须**配置 `API_KEY` |
| CORS | 默认 localhost | 必须设置 `CORS_ORIGINS` |

## Docker 本地验证

```bash
# 需先 export LLM_API_KEY、API_KEY 等
docker compose up --build
```

## 常见问题

**前端连不上 API**  
检查 `NEXT_PUBLIC_API_BASE` 是否含 `/api` 后缀，且前端已重新 build。

**401 未授权**  
确认前端 `NEXT_PUBLIC_API_KEY` 与后端 `API_KEY` 一致。

**pgvector 迁移失败**  
Render 部分套餐未开 vector 扩展；服务会降级为 JSON 向量检索，不影响主流程。

**冷启动慢**  
Render 免费/Starter 实例会休眠，首次请求需等待唤醒。

## 手动部署（不用 Blueprint）

### 后端 Web Service

- Runtime: **Docker**
- Root Directory: `backend`
- Health Check: `/health`
- Start Command:（Dockerfile 已包含）`./docker-entrypoint.sh`
- 挂载 Disk → `/app/storage`

### 前端 Web Service

- Runtime: **Docker**
- Root Directory: `frontend`
- Build 环境变量：`NEXT_PUBLIC_API_BASE`、`NEXT_PUBLIC_API_KEY`
