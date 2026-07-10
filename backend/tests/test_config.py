from __future__ import annotations

from pathlib import Path

from app.config import _BACKEND_DIR, _normalize_database_url


def test_sqlite_relative_database_url_resolves_from_backend_dir() -> None:
    url = _normalize_database_url("sqlite:///./fxpg.db")
    assert url == f"sqlite:///{(_BACKEND_DIR / 'fxpg.db').resolve()}"


def test_sqlite_absolute_database_url_is_preserved() -> None:
    absolute = Path("/tmp/fxpg-test.db")
    assert _normalize_database_url(f"sqlite:///{absolute}") == f"sqlite:///{absolute}"
