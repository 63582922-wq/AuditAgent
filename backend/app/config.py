from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://fxpg:fxpg@localhost:5432/fxpg"
    storage_path: Path = Path("./storage")

    # 文本 Agent（DeepSeek 等 OpenAI 兼容接口）
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.deepseek.com", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", validation_alias="LLM_MODEL")

    # 视觉模型（GLM-4.6V 等）
    vision_api_key: str = Field(default="", validation_alias="VISION_API_KEY")
    vision_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        validation_alias="VISION_BASE_URL",
    )
    vision_model: str = Field(default="glm-4.6v", validation_alias="VISION_MODEL")

    # 兼容旧变量名 OPENAI_*
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", validation_alias="OPENAI_BASE_URL")

    enable_llm: bool = True
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    api_key: str = ""
    max_upload_mb: int = 50
    job_workers: int = 2
    human_gate_manual_threshold: int = 5
    human_gate_manual_ratio: float = 0.45
    human_gate_high_threshold: int = 3
    human_gate_critic_threshold: int = 2
    enable_human_gate: bool = Field(default=False, validation_alias="ENABLE_HUMAN_GATE")
    enable_critic_llm: bool = True
    enable_critic_readjudicate: bool = Field(default=True, validation_alias="ENABLE_CRITIC_READJUDICATE")
    critic_readjudicate_max_rounds: int = Field(default=2, validation_alias="CRITIC_READJUDICATE_MAX_ROUNDS")
    agent_execution_mode: str = Field(default="orchestrator", validation_alias="AGENT_EXECUTION_MODE")
    enable_sub_agent_llm: bool = Field(default=True, validation_alias="ENABLE_SUB_AGENT_LLM")
    sub_agent_max_tool_turns: int = Field(default=4, validation_alias="SUB_AGENT_MAX_TOOL_TURNS")
    mcp_servers: str = Field(default="[]", validation_alias="MCP_SERVERS")
    react_max_turns: int = Field(default=16, validation_alias="REACT_MAX_TURNS")
    allowed_extensions: set[str] = {
        ".xlsx", ".xls", ".csv", ".docx", ".doc", ".pdf", ".jpg", ".jpeg", ".png",
    }

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
