from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(tags=["salud"])


@router.get("/health", summary="Sonda de salud")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "consulta_ine_habilitada": settings.consulta_ine_habilitada,
    }
