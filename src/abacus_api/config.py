from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/abacus.db"  # update to postgres for multi-host testing
    node_name: str = "local"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("ABACUS_DB_URL", cls.database_url),
            node_name=os.getenv("ABACUS_NODE_NAME", cls.node_name),
        )
