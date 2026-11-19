import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fineledger.demo import KEYS, build_scenario  # noqa: E402

TODAY = date(2026, 11, 19)


@pytest.fixture
def scenario(tmp_path):
    return build_scenario(TODAY, str(tmp_path / "ledger.jsonl"))


@pytest.fixture
def keys():
    return dict(KEYS)
