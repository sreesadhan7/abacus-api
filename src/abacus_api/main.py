from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from abacus_api.config import Settings
from abacus_api.db import AbacusStore, build_engine


class AddNumberRequest(BaseModel):
    number: int


class SumResponse(BaseModel):
    total: int


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    store = AbacusStore(build_engine(app_settings.database_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.initialize()
        app.state.store = store
        yield
        store.engine.dispose()

    app = FastAPI(title="Abacus API", lifespan=lifespan)

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "node": app_settings.node_name}

    @app.post("/abacus/number", response_model=SumResponse)
    def add_number(payload: AddNumberRequest) -> SumResponse:
        return SumResponse(total=app.state.store.add(payload.number))

    @app.get("/abacus/sum", response_model=SumResponse)
    def get_sum() -> SumResponse:
        return SumResponse(total=app.state.store.get_total())

    @app.delete("/abacus/sum", response_model=SumResponse)
    def reset_sum() -> SumResponse:
        return SumResponse(total=app.state.store.reset())

    return app


app = create_app()
