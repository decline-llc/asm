from pathlib import Path

import pytest

from asm.db import Database
from asm.scope import Scope


@pytest.fixture
def db():
    with Database(":memory:") as database:
        yield database


@pytest.fixture
def project():
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def local_scope():
    return Scope({"authorization": True, "targets": {"roots": ["localhost"],
        "ip_cidrs": ["127.0.0.1/32", "::1/128"]}}, target_local=True)
