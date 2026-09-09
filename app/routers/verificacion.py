"""Consulta contra la Lista Nominal del INE."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.core.clave_elector import analizar
from app.models.schemas import (
    ClaveElectorOut,
    Consulta,
    ConsultaModeloC,
    ResultadoConsulta,
)
from app.models.enums import EstatusLista
from app.services.ine_client import (
    BloqueoAntiBot,
    CaptchaRequerido,
    ErrorINE,
    INEClient,
)
from app.services.navegador import (
    CaptchaNoResuelto,
    NavegadorINE,
    PlaywrightNoInstalado,
)

router = APIRouter(prefix="/api/v1", tags=["consulta INE"])


def get_client(request: Request) -> INEClient:
    return request.app.state.ine_client


@router.post(
    "/verificacion",
    response_model=ResultadoConsulta,
    summary="Consulta una credencial en la Lista Nominal del INE",
    description=(
        "Reenvia los datos al formulario publico del INE. Requiere "
        "`captcha_token`: el token `g-recaptcha-response` que produce el "
        "reCAPTCHA v2 del sitio del INE al resolverlo. Esta API no resuelve "
        "el captcha por ti."
    ),
    responses={
        424: {"description": "Falta el token de reCAPTCHA o el INE lo rechazo"},
        502: {"description": "El INE no respondio o Cloudflare bloqueo la consulta"},
        503: {"description": "Las consultas salientes estan deshabilitadas"},
    },
)
async def verificar(
    consulta: Consulta = Body(...),
    cliente: INEClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> ResultadoConsulta:
    if not settings.consulta_ine_habilitada:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Las consultas al INE estan deshabilitadas (consulta_ine_habilitada=false). "
            "Usa /api/v1/validacion/clave-elector para validacion local.",
        )

    # El analisis local es gratis y atrapa errores de captura antes de
    # molestar al servidor del INE.
    analisis = None
    if isinstance(consulta, ConsultaModeloC):
        resultado = analizar(consulta.clave_elector)
        analisis = ClaveElectorOut(**resultado.__dict__)
        if not resultado.valida:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"mensaje": "La clave de elector no es estructuralmente valida", "errores": resultado.errores},
            )

    try:
        estatus, mensaje, momento = await cliente.consultar(consulta)
    except CaptchaRequerido as exc:
        raise HTTPException(status.HTTP_424_FAILED_DEPENDENCY, str(exc)) from exc
    except BloqueoAntiBot as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except ErrorINE as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return ResultadoConsulta(
        modelo=consulta.modelo,
        estatus=estatus,
        encontrado=estatus is EstatusLista.VIGENTE,
        mensaje=mensaje,
        consultado_en=momento,
        analisis_clave=analisis,
    )


@router.post(
    "/verificacion/asistida",
    response_model=ResultadoConsulta,
    summary="Consulta abriendo un navegador; el captcha lo marca una persona",
    description=(
        "Abre Chromium **con interfaz**, captura los campos del formulario del "
        "INE automaticamente y espera a que una persona marque el reCAPTCHA. "
        "Al marcarlo, envia y parsea el resultado sin mas intervencion.\n\n"
        "Automatiza todo salvo el clic del captcha, que es precisamente el "
        "control que distingue a una persona de un programa.\n\n"
        "Requiere `pip install playwright && playwright install chromium`, y "
        "un entorno con escritorio: no funciona en un servidor headless."
    ),
    responses={
        408: {"description": "Nadie marco el reCAPTCHA a tiempo"},
        501: {"description": "Playwright no esta instalado"},
        502: {"description": "El navegador no pudo completar la consulta"},
    },
)
async def verificar_asistida(
    consulta: Consulta = Body(...),
    settings: Settings = Depends(get_settings),
) -> ResultadoConsulta:
    if not settings.consulta_ine_habilitada:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Las consultas al INE estan deshabilitadas (consulta_ine_habilitada=false).",
        )

    analisis = None
    if isinstance(consulta, ConsultaModeloC):
        resultado = analizar(consulta.clave_elector)
        analisis = ClaveElectorOut(**resultado.__dict__)
        if not resultado.valida:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"mensaje": "La clave de elector no es estructuralmente valida", "errores": resultado.errores},
            )

    navegador = NavegadorINE(settings)
    try:
        estatus, mensaje, momento = await navegador.consultar_asistido(consulta)
    except PlaywrightNoInstalado as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc
    except CaptchaNoResuelto as exc:
        raise HTTPException(status.HTTP_408_REQUEST_TIMEOUT, str(exc)) from exc
    except ErrorINE as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return ResultadoConsulta(
        modelo=consulta.modelo,
        estatus=estatus,
        encontrado=estatus is EstatusLista.VIGENTE,
        mensaje=mensaje,
        consultado_en=momento,
        analisis_clave=analisis,
    )
