from pathlib import Path

import pytest

from app.exceptions import FXPGError
from app.services.domain.compliance.case_upload import safe_relative_path


def test_safe_relative_path():
    assert safe_relative_path("FX/sample.pdf") == Path("FX", "sample.pdf")
    assert safe_relative_path("sample.pdf") == Path("sample.pdf")


def test_safe_relative_path_rejects_traversal():
    with pytest.raises(FXPGError):
        safe_relative_path("..")
    with pytest.raises(FXPGError):
        safe_relative_path("")
    # 去掉 .. 后仍落在 staging 目录内
    assert safe_relative_path("../etc/passwd") == Path("etc", "passwd")
