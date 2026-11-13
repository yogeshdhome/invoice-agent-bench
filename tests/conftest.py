import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from invoice_bench.data.generate import generate
from invoice_bench.security.auth import SERVICE_PRINCIPAL, Principal, issue_token
from invoice_bench.services.app import create_app
from invoice_bench.services.faults import FaultController

SEED = 20261111


@pytest.fixture(scope="session")
def dataset(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("ds") / "v1"
    generate(SEED, d)
    return d


@pytest.fixture
def world_db(dataset, tmp_path) -> Path:
    p = tmp_path / "world.sqlite"
    shutil.copy(dataset / "world.sqlite", p)
    return p


@pytest.fixture
def faults():
    return FaultController()


@pytest.fixture
def client(world_db, faults):
    return TestClient(create_app(str(world_db), faults=faults, today="2026-11-02"))


def bearer(p: Principal) -> dict:
    return {"Authorization": f"Bearer {issue_token(p)}"}


CLERK_A1 = Principal(user_id="u-alpha-clerk-1", tenant_id="t-alpha", bu_ids=("bu-alpha-1",), roles=("AP_CLERK",))
SUP_A = Principal(user_id="u-alpha-supervisor-1", tenant_id="t-alpha", bu_ids=("bu-alpha-1", "bu-alpha-2"), roles=("AP_SUPERVISOR",))
CLERK_B1 = Principal(user_id="u-beta-clerk-1", tenant_id="t-beta", bu_ids=("bu-beta-1",), roles=("AP_CLERK",))
SVC = SERVICE_PRINCIPAL
