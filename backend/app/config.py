from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_ENV_FILE = _BACKEND_DIR / ".env"

_DEFAULT_CORS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]


def _normalize_database_url(url: str) -> str:
    """Render 等托管返回 postgres://，SQLAlchemy 需 postgresql+psycopg2://。"""
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        raw_path = url[len("sqlite:///") :]
        if raw_path and raw_path != ":memory:":
            path = Path(raw_path)
            if not path.is_absolute():
                return f"sqlite:///{(_BACKEND_DIR / path).resolve()}"
    if url == "sqlite:///:memory:":
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg2" not in url and "+asyncpg" not in url:
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    database_url: str = "postgresql+psycopg2://fxpg:fxpg@localhost:5432/fxpg"
    storage_path: Path = _BACKEND_DIR / "storage"

    # 文本 Agent（DeepSeek 等 OpenAI 兼容接口）
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.deepseek.com", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", validation_alias="LLM_MODEL")

    # 视觉模型（GLM-OCR / GLM-V 等）
    vision_api_key: str = Field(default="", validation_alias="VISION_API_KEY")
    vision_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        validation_alias="VISION_BASE_URL",
    )
    vision_model: str = Field(default="glm-ocr", validation_alias="VISION_MODEL")
    vision_retry_max: int = Field(default=5, validation_alias="VISION_RETRY_MAX")
    vision_retry_base_sec: float = Field(default=2.0, validation_alias="VISION_RETRY_BASE_SEC")
    vision_inter_request_delay_sec: float = Field(
        default=0.8, validation_alias="VISION_INTER_REQUEST_DELAY_SEC"
    )
    vision_max_workers: int = Field(default=3, validation_alias="VISION_MAX_WORKERS")
    vision_high_risk_min_passes: int = Field(default=2, validation_alias="VISION_HIGH_RISK_MIN_PASSES")
    pdf_vision_max_pages: int = Field(default=120, validation_alias="PDF_VISION_MAX_PAGES")

    # 兼容旧变量名 OPENAI_*
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", validation_alias="OPENAI_BASE_URL")

    enable_llm: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: list(_DEFAULT_CORS))
    api_key: str = ""
    max_upload_mb: int = 50
    job_workers: int = 2
    job_recovery_stale_sec: int = Field(default=300, validation_alias="JOB_RECOVERY_STALE_SEC")
    human_gate_manual_threshold: int = 5
    human_gate_manual_ratio: float = 0.45
    human_gate_high_threshold: int = 3
    human_gate_critic_threshold: int = 2
    enable_human_gate: bool = Field(default=False, validation_alias="ENABLE_HUMAN_GATE")
    enable_critic_llm: bool = True
    enable_critic_readjudicate: bool = Field(default=True, validation_alias="ENABLE_CRITIC_READJUDICATE")
    critic_readjudicate_max_rounds: int = Field(default=2, validation_alias="CRITIC_READJUDICATE_MAX_ROUNDS")
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    bootstrap_data_on_startup: bool = Field(default=False, validation_alias="BOOTSTRAP_DATA_ON_STARTUP")
    sync_pgvector_on_startup: bool = Field(default=False, validation_alias="SYNC_PGVECTOR_ON_STARTUP")
    allow_server_case_path: bool = Field(default=False, validation_alias="ALLOW_SERVER_CASE_PATH")
    agent_domain: str = Field(default="compliance", validation_alias="AGENT_DOMAIN")
    agent_execution_mode: str = Field(default="orchestrator", validation_alias="AGENT_EXECUTION_MODE")
    enable_sub_agent_llm: bool = Field(default=True, validation_alias="ENABLE_SUB_AGENT_LLM")
    sub_agent_max_tool_turns: int = Field(default=4, validation_alias="SUB_AGENT_MAX_TOOL_TURNS")
    mcp_servers: str = Field(default="[]", validation_alias="MCP_SERVERS")
    react_max_turns: int = Field(default=16, validation_alias="REACT_MAX_TURNS")
    allowed_extensions: set[str] = {
        ".xlsx", ".xls", ".csv", ".docx", ".doc", ".pdf", ".jpg", ".jpeg", ".png",
    }

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        if isinstance(v, str):
            return _normalize_database_url(v)
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        if v is None or v == "":
            return list(_DEFAULT_CORS)
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def text_api_key(self) -> str:
        return self.llm_api_key or self.openai_api_key

    @property
    def text_base_url(self) -> str:
        return self.llm_base_url or self.openai_base_url or "https://api.deepseek.com"

    @property
    def text_model(self) -> str:
        return self.llm_model


settings = Settings()
settings.storage_path.mkdir(parents=True, exist_ok=True)
(settings.storage_path / "uploads").mkdir(exist_ok=True)
(settings.storage_path / "outputs").mkdir(exist_ok=True)
