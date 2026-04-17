from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.utils.config import Settings, get_settings

app = FastAPI(title="Media Traffic AI Analyst")

SettingsDep = Annotated[Settings, Depends(get_settings)]


class HealthResponse(BaseModel):
    status: str
    environment: str


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)
