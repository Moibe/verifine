"""Pruebas del parser contra la estructura REAL de resultado.html.

El fixture tests/fixtures/resultado_vigente.html es una respuesta autentica del
INE (consulta del 2026-09-10, modelo E) con todos los datos personales
sustituidos por valores ficticios.
"""

import pathlib

import pytest

from app.models.enums import EstatusLista
from app.services.parser import clasificar, extraer_texto, parsear, parsear_resultado

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def html_vigente() -> str:
    return (FIXTURES / "resultado_vigente.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Contra la respuesta real
# --------------------------------------------------------------------------
def test_respuesta_real_se_clasifica_vigente(html_vigente):
    assert parsear(html_vigente).estatus is EstatusLista.VIGENTE


def test_veredicto_es_el_del_ine_no_el_encabezado(html_vigente):
    """El veredicto debe salir del bloque de resultado, no del banner."""
    veredicto = parsear(html_vigente).veredicto
    assert "vigente como medio de identificación" in veredicto
    assert "Padrón Electoral" in veredicto
    # El encabezado fijo del portal no debe aparecer en el veredicto.
    assert "¿Está vigente tu credencial?" not in veredicto
    # Ni el pie de ayuda.
    assert "Preguntas Frecuentes" not in veredicto
    assert "Necesitas ayuda" not in veredicto


def test_extrae_la_tabla_de_datos(html_vigente):
    campos = parsear(html_vigente).campos
    assert campos["CIC"] == "111111111"
    assert campos["Clave de elector"] == "ABCDEF90010109H123"
    assert campos["Número de emisión"] == "1"
    assert campos["Distrito Federal"] == "9"
    assert campos["Distrito Local"] == "9"
    assert campos["Número OCR"] == "0000000000001"
    assert campos["Año de registro"] == "2012"
    assert campos["Año de emisión"] == "2023"


def test_vigencia_no_arrastra_el_pie_de_pagina(html_vigente):
    """Regresion: el patron abierto se traia '... de 2033 Preguntas Frecuentes'."""
    assert parsear(html_vigente).vigencia_hasta == "31 de diciembre de 2033"


def test_separa_las_fechas_del_ine(html_vigente):
    r = parsear(html_vigente)
    assert r.fecha_consulta == "10 de septiembre del 2026"
    assert r.fecha_actualizacion == "10 de septiembre del 2026 03:01"
    # Y no deben contaminar el veredicto.
    assert "Fecha de consulta" not in r.veredicto


# --------------------------------------------------------------------------
# El falso positivo que costo descubrir
# --------------------------------------------------------------------------
def test_el_encabezado_del_portal_no_dicta_veredicto():
    """El banner "¿Está vigente tu credencial?" sale en TODAS las respuestas,
    incluidas las negativas. Nunca debe producir un veredicto por si solo."""
    solo_boilerplate = """
    <html><body>
      <h2>¿Está vigente tu credencial?</h2>
      <h2>Sólo con las credenciales vigentes pueden votar.</h2>
      <p>Tema: INICIO / RESULTADO</p>
    </body></html>
    """
    assert parsear(solo_boilerplate).estatus is EstatusLista.INDETERMINADO


def test_encabezado_no_tapa_un_veredicto_negativo():
    """Caso peligroso: banner positivo + veredicto negativo. Debe ganar el
    veredicto, si no reportariamos como vigente una credencial que no lo es."""
    html = """
    <html><body>
      <h2>¿Está vigente tu credencial?</h2>
      <table><tr><td><strong>CIC</strong></td><td>111111111</td></tr></table>
      <h4>Tu credencial perdió vigencia.</h4>
    </body></html>
    """
    assert parsear(html).estatus is EstatusLista.NO_VIGENTE


# --------------------------------------------------------------------------
# Clasificacion sobre frases sueltas
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Esta vigente como medio de identificación.", EstatusLista.VIGENTE),
        ("Tus datos se encuentran en el Padrón Electoral.", EstatusLista.VIGENTE),
        ("El ciudadano se encuentra en la Lista Nominal", EstatusLista.VIGENTE),
        ("Tu credencial perdió vigencia", EstatusLista.NO_VIGENTE),
        ("La credencial ya no es válida", EstatusLista.NO_VIGENTE),
        ("El registro no se encuentra", EstatusLista.NO_ENCONTRADO),
        ("No fue localizado en el padrón", EstatusLista.NO_ENCONTRADO),
        ("Credencial reportada como robada", EstatusLista.ROBO_EXTRAVIO),
        ("Reporte de extravío vigente", EstatusLista.ROBO_EXTRAVIO),
        ("Los datos no coinciden", EstatusLista.DATOS_NO_COINCIDEN),
        ("Respuesta que nadie previo", EstatusLista.INDETERMINADO),
    ],
)
def test_clasificacion_de_frases(texto, esperado):
    assert clasificar(texto) is esperado


def test_vigente_no_se_confunde_con_ciudadano():
    """Regresion: "ciudadano se encuentra" contiene "no se encuentra"."""
    assert clasificar("El ciudadano se encuentra en la Lista Nominal") is EstatusLista.VIGENTE


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def test_extraer_texto_quita_scripts():
    assert extraer_texto("<html><script>var a=1;</script><p>Hola  mundo</p></html>") == "Hola mundo"


def test_forma_corta_sigue_funcionando(html_vigente):
    estatus, mensaje = parsear_resultado(html_vigente)
    assert estatus is EstatusLista.VIGENTE
    assert "Padrón Electoral" in mensaje
