from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    admin,
    auth,
    campaigns,
    chat,
    coaching,
    employee,
    health,
    hr,
    integrations,
)
from app.api import realtime as realtime_api
from app.agents.campaign_graph import CampaignGenerationError
from app.services.config import ConfigMissingError, get_settings, validate_runtime_settings
from app.services.llm_gateway import LLMUnavailableError

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_settings()  # refuse to start half-configured instead of degrading silently
    yield


app = FastAPI(title="PhishCoach AI API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(_: Request, exc: LLMUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": f"AI service unavailable: {exc}"})


@app.exception_handler(CampaignGenerationError)
async def campaign_generation_handler(_: Request, exc: CampaignGenerationError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"{exc}. Please retry."})


@app.exception_handler(ConfigMissingError)
async def config_missing_handler(_: Request, exc: ConfigMissingError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"Server configuration error: {exc}"})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(employee.router)
app.include_router(coaching.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(hr.router)
app.include_router(integrations.router)
app.include_router(realtime_api.router)
