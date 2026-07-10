from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.database import SessionLocal, init_db
from app.exceptions import FXPGError, fxpg_exception_handler, generic_exception_handler
from app.logging_config import setup_logging
from app.services.jobs.worker import get_executor, recover_pending_jobs
from app.services.seed import seed_memories, seed_rules, sync_pgvector_from_json


def _should_bootstrap_data() -> bool:
    return settings.bootstrap_data_on_startup or settings.app_env.lower() == "production"


def _should_sync_vectors() -> bool:
    return settings.sync_pgvector_on_startup or settings.app_env.lower() == "production"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    if settings.app_env.lower() == "production" and not settings.api_key:
        logging.getLogger(__name__).error("APP_ENV=production 但未配置 API_KEY，API 将拒绝所有请求")
    init_db()
    db = SessionLocal()
    try:
        if _should_bootstrap_data():
            seed_rules(db)
            seed_memories(db)
        if _should_sync_vectors():
            sync_pgvector_from_json(db)
    finally:
        db.close()
    recovered = recover_pending_jobs()
    if recovered:
        logging.getLogger(__name__).info("Recovered %s persisted analysis job(s)", recovered)
    try:
        yield
    finally:
        # 优雅关闭线程池：等待正在执行的 analysis 任务完成，最多 30 秒
        get_executor().shutdown(wait=True, cancel_futures=False)


app = FastAPI(title="AuditAgent 会议合规远程观察", version="2.4.0", lifespan=lifespan)
app.add_exception_handler(FXPGError, fxpg_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.4.0"}
