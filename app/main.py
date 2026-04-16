from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel
from app.utils.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)

class HealthResponse(BaseModel):
    status: str
    environment: str

@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)
