from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.database import SessionLocal, init_db
from app.exceptions import FXPGError, fxpg_exception_handler, generic_exception_handler
from app.logging_config import setup_logging
from app.services.seed import seed_memories, seed_rules, sync_pgvector_from_json


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    init_db()
    db = SessionLocal()
    try:
        seed_rules(db)
        seed_memories(db)
        sync_pgvector_from_json(db)
    finally:
        db.close()
    yield


app = FastAPI(title="FXPG 会计风险评估 Agent", version="2.4.0", lifespan=lifespan)
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
    from app.services.agent.llm_client import llm_available
    from app.services.vision_client import vision_available

    return {
        "status": "ok" if llm_available() else "degraded",
        "version": "2.4.0",
        "mode": "agent_only",
        "agent_ready": llm_available(),
        "text_model": settings.llm_model,
        "vision_model": settings.vision_model,
        "vision_ready": vision_available(),
    }
