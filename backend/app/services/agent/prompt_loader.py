from __future__ import annotations

from functools import lru_cache
from pathlib import Path


MAIN_AGENT_PROMPT_VERSION = "main-agent-evidence-v1"
_PROMPT_DIR = Path(__file__).with_name("prompts")


@lru_cache(maxsize=8)
def load_system_prompt(name: str) -> str:
    """Load a versioned system prompt from source instead of burying it in code."""
    path = _PROMPT_DIR / name
    return path.read_text(encoding="utf-8").strip()


def main_agent_system_prompt() -> str:
    return load_system_prompt("main_agent.system.md")
