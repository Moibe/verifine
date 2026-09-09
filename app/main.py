from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, validacion, verificacion
from app.services.ine_client import INEClient

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ine_client = INEClient(settings)
    try:
        yield
    finally:
        await app.state.ine_client.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Validacion de credenciales para votar (INE).\n\n"
        "- `/api/v1/validacion/*` valida la estructura de los datos en local.\n"
        "- `/api/v1/verificacion` consulta la Lista Nominal publica del INE; "
        "exige un token de reCAPTCHA resuelto por una persona."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(validacion.router)
app.include_router(verificacion.router)
