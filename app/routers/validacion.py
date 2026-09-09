"""Validacion local: no sale a internet, no toca al INE."""

from fastapi import APIRouter

from app.core.clave_elector import analizar
from app.core.entidades import ENTIDADES
from app.models.schemas import ClaveElectorOut, Entidad, ValidacionClaveRequest

router = APIRouter(prefix="/api/v1", tags=["validacion local"])


@router.post(
    "/validacion/clave-elector",
    response_model=ClaveElectorOut,
    summary="Analiza la estructura de una clave de elector",
    description=(
        "Descompone la clave en sus componentes y verifica que la forma sea "
        "coherente. NO consulta al INE: una clave estructuralmente valida "
        "puede no existir en el padron."
    ),
)
def validar_clave(payload: ValidacionClaveRequest) -> ClaveElectorOut:
    return ClaveElectorOut(**analizar(payload.clave_elector).__dict__)


@router.get(
    "/catalogos/entidades",
    response_model=list[Entidad],
    summary="Catalogo de entidades federativas (claves 01-32)",
)
def listar_entidades() -> list[Entidad]:
    return [Entidad(clave=c, nombre=n) for c, n in sorted(ENTIDADES.items())]
