"""Cliente HTTP contra el servicio publico de Lista Nominal del INE.

Sobre el reCAPTCHA
------------------
Los cuatro formularios de https://listanominal.ine.mx/scpln/ estan protegidos
con Google reCAPTCHA v2 y el sitio esta detras de Cloudflare. Este cliente NO
intenta evadir ninguno de los dos: exige que quien llama entregue un
`captcha_token` ya resuelto y lo reenvia como `g-recaptcha-response`. Si el
token es invalido o falta, el INE respondera con un error y lo propagamos tal
cual.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

from app.config import Settings
from app.models.enums import EstatusLista, ModeloCredencial
from app.models.schemas import (
    ConsultaModeloC,
    ConsultaModeloD,
    ConsultaModeloEFGH,
    ConsultaReporte,
)
from app.services.parser import ResultadoParseado, parsear


class ErrorINE(RuntimeError):
    """El INE no pudo atender la consulta."""


class CaptchaRequerido(ErrorINE):
    """Falta el token de reCAPTCHA, o el INE lo rechazo."""


class BloqueoAntiBot(ErrorINE):
    """Cloudflare interpuso un challenge; la consulta no llego al INE."""


def construir_payload(consulta) -> dict[str, str]:
    """Traduce el esquema de la API a los names exactos del formulario."""
    if isinstance(consulta, ConsultaModeloC):
        datos = {
            "modelo": ModeloCredencial.C.value,
            "claveElector": consulta.clave_elector,
            "numeroEmision": consulta.numero_emision,
            "ocr": consulta.ocr,
        }
    elif isinstance(consulta, ConsultaModeloD):
        datos = {
            "modelo": ModeloCredencial.D.value,
            "cic": consulta.cic,
            "ocr": consulta.ocr,
        }
    elif isinstance(consulta, ConsultaModeloEFGH):
        datos = {
            "modelo": ModeloCredencial.E.value,
            "cic": consulta.cic,
            "idCiudadano": consulta.id_ciudadano,
        }
    elif isinstance(consulta, ConsultaReporte):
        datos = {
            "modelo": ModeloCredencial.R.value,
            "numeroReporteRoboExtravio": consulta.numero_reporte,
        }
    else:  # pragma: no cover - la union discriminada lo impide
        raise ValueError(f"Modelo no soportado: {type(consulta)!r}")

    datos["g-recaptcha-response"] = consulta.captcha_token or ""
    return datos


def _parece_challenge(html: str) -> bool:
    marcadores = ("Just a moment", "cf_chl_opt", "challenge-platform", "cf-mitigated")
    return any(m in html for m in marcadores)


class INEClient:
    def __init__(self, settings: Settings, cliente: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._cliente = cliente or httpx.AsyncClient(
            timeout=settings.ine_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": settings.ine_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-MX,es;q=0.9",
                "Origin": "https://listanominal.ine.mx",
                "Referer": settings.ine_base_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    async def aclose(self) -> None:
        await self._cliente.aclose()

    async def _sembrar_cookies(self) -> None:
        """Visita la pagina del formulario para recoger las cookies de sesion
        (INEPool, __cf_bm) antes de enviar el POST, como haria un navegador."""
        try:
            await self._cliente.get(self._settings.ine_base_url)
        except httpx.HTTPError:
            # Que falle el precalentamiento no debe abortar la consulta.
            pass

    async def consultar(self, consulta) -> tuple[ResultadoParseado, str]:
        """Devuelve (resultado parseado, marca de tiempo ISO-8601)."""
        if not consulta.captcha_token:
            raise CaptchaRequerido(
                "El formulario del INE exige reCAPTCHA. Envia el token en `captcha_token`."
            )

        await self._sembrar_cookies()

        url = urljoin(self._settings.ine_base_url, self._settings.ine_resultado_path)
        try:
            respuesta = await self._cliente.post(url, data=construir_payload(consulta))
        except httpx.HTTPError as exc:
            raise ErrorINE(f"No se pudo contactar al INE: {exc}") from exc

        cuerpo = respuesta.text
        momento = datetime.now(timezone.utc).isoformat()

        if respuesta.status_code in (403, 429, 503) or _parece_challenge(cuerpo):
            raise BloqueoAntiBot(
                "Cloudflare interpuso un challenge (HTTP "
                f"{respuesta.status_code}). La consulta no llego al INE."
            )

        if respuesta.status_code >= 400:
            raise ErrorINE(f"El INE respondio HTTP {respuesta.status_code}")

        resultado = parsear(cuerpo)

        if resultado.estatus is EstatusLista.INDETERMINADO and "captcha" in cuerpo.lower():
            raise CaptchaRequerido("El INE rechazo el token de reCAPTCHA.")

        return resultado, momento
