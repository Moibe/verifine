"""Pruebas del modulo de navegador.

Ninguna lanza Chromium: se sustituye `_flujo` por dobles que simulan los
fallos que vimos en la practica.
"""

import pytest

from app.config import Settings
from app.models.schemas import ConsultaModeloEFGH
from app.services.navegador import (
    CaptchaNoResuelto,
    ErrorDriver,
    NavegadorINE,
    _es_fallo_de_driver,
    _valores_formulario,
)


@pytest.fixture
def consulta():
    return ConsultaModeloEFGH(cic="111111111", id_ciudadano="222222222")


@pytest.fixture
def settings():
    return Settings(navegador_reintentos=3)


# --------------------------------------------------------------------------
# Reconocer un driver caido
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mensaje",
    [
        "Connection closed while reading from the driver",
        "Connection.init: Connection closed while reading from the driver",
        "Target closed",
        "Browser has been closed",
    ],
)
def test_reconoce_fallos_de_driver(mensaje):
    assert _es_fallo_de_driver(Exception(mensaje)) is True


@pytest.mark.parametrize(
    "mensaje",
    [
        "Timeout 15000ms exceeded waiting for selector",
        "El INE respondio HTTP 500",
        "strict mode violation: locator resolved to 2 elements",
    ],
)
def test_no_confunde_otros_errores_con_el_driver(mensaje):
    assert _es_fallo_de_driver(Exception(mensaje)) is False


# --------------------------------------------------------------------------
# Reintentos
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reintenta_cuando_el_driver_muere_al_arrancar(consulta, settings, monkeypatch):
    """El caso real: node.exe muere en el handshake. Debe reintentar."""
    intentos = {"n": 0}

    async def flujo_que_falla_una_vez(*args, **kwargs):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise Exception("Connection closed while reading from the driver")
        return ("RESULTADO", "2026-01-01T00:00:00Z")

    nav = NavegadorINE(settings)
    monkeypatch.setattr(nav, "_flujo", flujo_que_falla_una_vez)

    resultado, momento = await nav.consultar_asistido(consulta)
    assert resultado == "RESULTADO"
    assert intentos["n"] == 2, "debio reintentar exactamente una vez"


@pytest.mark.asyncio
async def test_se_rinde_tras_agotar_los_reintentos(consulta, settings, monkeypatch):
    intentos = {"n": 0}

    async def siempre_falla(*args, **kwargs):
        intentos["n"] += 1
        raise Exception("Connection closed while reading from the driver")

    nav = NavegadorINE(settings)
    monkeypatch.setattr(nav, "_flujo", siempre_falla)

    with pytest.raises(ErrorDriver) as exc:
        await nav.consultar_asistido(consulta)

    assert intentos["n"] == 3
    # El mensaje debe orientar, no solo repetir el error de Playwright.
    assert "antivirus" in str(exc.value).lower()
    assert "diagnostico" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_no_reintenta_errores_que_no_son_del_driver(consulta, settings, monkeypatch):
    """Un selector que no aparece volveria a no aparecer: reintentar es inutil."""
    intentos = {"n": 0}

    async def falla_por_selector(*args, **kwargs):
        intentos["n"] += 1
        raise Exception("Timeout 15000ms exceeded waiting for selector")

    nav = NavegadorINE(settings)
    monkeypatch.setattr(nav, "_flujo", falla_por_selector)

    with pytest.raises(Exception, match="Timeout"):
        await nav.consultar_asistido(consulta)
    assert intentos["n"] == 1


@pytest.mark.asyncio
async def test_no_reintenta_si_ya_se_pidio_el_captcha(consulta, settings, monkeypatch):
    """Reabrir el navegador tras pedir el captcha obligaria a la persona a
    marcarlo otra vez sin explicacion. No se hace."""
    intentos = {"n": 0}

    async def falla_despues_del_captcha(async_pw, PWTimeout, cfg, valores, guardar, avisar, estado):
        intentos["n"] += 1
        estado["pidio_captcha"] = True
        raise Exception("Connection closed while reading from the driver")

    nav = NavegadorINE(settings)
    monkeypatch.setattr(nav, "_flujo", falla_despues_del_captcha)

    with pytest.raises(ErrorDriver):
        await nav.consultar_asistido(consulta)
    assert intentos["n"] == 1, "no debe reintentar tras involucrar a la persona"


@pytest.mark.asyncio
async def test_captcha_no_resuelto_no_se_reintenta(consulta, settings, monkeypatch):
    intentos = {"n": 0}

    async def nadie_marco(*args, **kwargs):
        intentos["n"] += 1
        raise CaptchaNoResuelto("Nadie marco el reCAPTCHA en 180 s.")

    nav = NavegadorINE(settings)
    monkeypatch.setattr(nav, "_flujo", nadie_marco)

    with pytest.raises(CaptchaNoResuelto):
        await nav.consultar_asistido(consulta)
    assert intentos["n"] == 1


# --------------------------------------------------------------------------
# Mapeo de campos al formulario del INE
# --------------------------------------------------------------------------
def test_valores_formulario_usa_los_names_del_ine(consulta):
    valores = _valores_formulario(consulta)
    assert valores == {"cic": "111111111", "idCiudadano": "222222222"}
    # El token de captcha y el modelo no son campos a capturar.
    assert "g-recaptcha-response" not in valores
    assert "modelo" not in valores
