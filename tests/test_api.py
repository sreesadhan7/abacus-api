from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from abacus_api.config import Settings
from abacus_api.db import AbacusStore, build_engine
from abacus_api.main import create_app


def test_sum_is_shared_across_two_app_instances(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'abacus.db'}"
    app_one = create_app(Settings(database_url=database_url))
    app_two = create_app(Settings(database_url=database_url))

    with TestClient(app_one) as client_one, TestClient(app_two) as client_two:
        assert client_one.post("/abacus/number", json={"number": 7}).json() == {"total": 7}
        assert client_two.post("/abacus/number", json={"number": 5}).json() == {"total": 12}
        assert client_one.get("/abacus/sum").json() == {"total": 12}
        assert client_two.delete("/abacus/sum").json() == {"total": 0}
        assert client_one.get("/abacus/sum").json() == {"total": 0}


def test_concurrent_adds_keep_the_expected_total(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'abacus.db'}"
    store = AbacusStore(build_engine(database_url))
    store.initialize()

    def add_one() -> int:
        return store.add(1)

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(lambda _: add_one(), range(120)))

    assert store.get_total() == 120
