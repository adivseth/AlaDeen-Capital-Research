from pathlib import Path

import pytest

from aladeen.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg(tmp_path):
    return load_config({"home_dir": str(tmp_path / "home"), "results_dir": str(tmp_path / "results")},
                       use_env=False)


@pytest.fixture
def tcs_html():
    return (FIXTURES / "screener_tcs.html").read_text(encoding="utf-8")


@pytest.fixture
def tcs_peers_html():
    return (FIXTURES / "screener_peers_tcs.html").read_text(encoding="utf-8")
