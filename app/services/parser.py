"""Interpreta el HTML que devuelve `resultado.html` del INE.

El INE no publica un contrato: la respuesta es una pagina pensada para leerse.
Por eso el parser es deliberadamente tolerante: extrae el texto visible, lo
compara contra patrones conocidos y SIEMPRE conserva el mensaje original para
que quien consuma la API pueda juzgar por si mismo cuando el patron falle.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.models.enums import EstatusLista

# El orden importa: se evalua de arriba hacia abajo y gana el primero.
#
# Los \b de las negaciones no son decorativos: sin ellos "no se encuentra"
# coincide dentro de "ciudadaNO SE ENCUENTRA" y un caso vigente se clasifica
# exactamente al reves.
_PATRONES: list[tuple[EstatusLista, re.Pattern[str]]] = [
    (
        EstatusLista.ROBO_EXTRAVIO,
        re.compile(r"\brob(o|ada|ado)\b|\bextrav[ií]", re.I),
    ),
    (
        EstatusLista.NO_VIGENTE,
        re.compile(
            r"perdi[oó]\s+(su\s+)?vigencia|\bno\s+(est[aá]\s+)?vigente\b|vigencia\s+venci",
            re.I,
        ),
    ),
    (
        EstatusLista.DATOS_NO_COINCIDEN,
        re.compile(r"datos\s+\bno\s+coinciden\b|\bno\s+coincide", re.I),
    ),
    (
        EstatusLista.NO_ENCONTRADO,
        re.compile(
            r"\bno\s+se\s+encuentra\b|\bno\s+fue\s+localizad|sin\s+resultado|\bno\s+existe\b",
            re.I,
        ),
    ),
    (
        EstatusLista.VIGENTE,
        re.compile(
            r"se\s+encuentra\s+en\s+la\s+lista\s+nominal|est[aá]\s+vigente\b|s[ií]\s+se\s+encuentra",
            re.I,
        ),
    ),
]


def extraer_texto(html: str) -> str:
    sopa = BeautifulSoup(html, "lxml")
    for etiqueta in sopa(["script", "style", "noscript"]):
        etiqueta.decompose()
    return re.sub(r"\s+", " ", sopa.get_text(separator=" ", strip=True)).strip()


def clasificar(texto: str) -> EstatusLista:
    for estatus, patron in _PATRONES:
        if patron.search(texto):
            return estatus
    return EstatusLista.INDETERMINADO


def _mensaje_relevante(texto: str) -> str:
    """Recorta el boilerplate del portal y se queda con la frase util."""
    for _, patron in _PATRONES:
        coincidencia = patron.search(texto)
        if coincidencia:
            inicio = max(0, coincidencia.start() - 160)
            fin = min(len(texto), coincidencia.end() + 160)
            return texto[inicio:fin].strip()
    return texto[:500].strip()


def parsear_resultado(html: str) -> tuple[EstatusLista, str]:
    texto = extraer_texto(html)
    estatus = clasificar(texto)
    return estatus, _mensaje_relevante(texto)
