"""Interpreta el HTML que devuelve `resultado.html` del INE.

Estructura real de la respuesta (verificada contra una consulta en vivo el
2026-09-10, modelo E):

    <table> ... <tr><td><strong>Campo</strong></td><td>valor</td></tr> ... </table>
    <p class="lead">Fecha de actualizacion ...</p>
    <p class="lead">Fecha de consulta ...</p>
    <h4 style="color:#d50080;">Esta vigente como medio de identificacion.</h4>
    <p class="lead">Tus datos se encuentran en el Padron Electoral.</p>
    <h4><mark>Sera valida hasta el 31 de diciembre de 2033</mark></h4>

Dos lecciones de esa consulta, que explican el diseno de aqui abajo:

1. El veredicto NO se puede buscar en toda la pagina. El portal lleva un
   encabezado fijo que dice "Esta vigente tu credencial?" en TODAS las
   respuestas, incluidas las negativas. Buscar "esta vigente" en el texto
   completo da un falso positivo garantizado. Por eso clasificamos solo dentro
   del bloque de veredicto.
2. El INE responde "Padron Electoral", no "Lista Nominal". La frase que
   buscabamos antes no aparece nunca.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from app.models.enums import EstatusLista

# Se evalua en orden y gana el primero. Estos patrones se aplican SOLO al
# bloque de veredicto, nunca a la pagina completa.
_PATRONES: list[tuple[EstatusLista, re.Pattern[str]]] = [
    (
        EstatusLista.ROBO_EXTRAVIO,
        re.compile(r"\brob(o|ada|ado)\b|\bextrav[ií]|report(ada|ado)\s+como", re.I),
    ),
    (
        EstatusLista.NO_VIGENTE,
        re.compile(
            r"perdi[oó]\s+(su\s+)?vigencia|\bno\s+(est[aá]\s+)?vigente\b"
            r"|vigencia\s+venci|\bya\s+no\s+es\s+v[aá]lida\b",
            re.I,
        ),
    ),
    (
        EstatusLista.DATOS_NO_COINCIDEN,
        re.compile(r"\bno\s+coincide|datos\s+incorrectos|verifica\s+tus\s+datos", re.I),
    ),
    (
        EstatusLista.NO_ENCONTRADO,
        re.compile(
            r"\bno\s+se\s+encuentra\b|\bno\s+fue\s+localizad|sin\s+resultado"
            r"|\bno\s+existe\b|\bno\s+localizad",
            re.I,
        ),
    ),
    (
        EstatusLista.VIGENTE,
        re.compile(
            r"vigente\s+como\s+medio\s+de\s+identificaci[oó]n"
            r"|datos\s+se\s+encuentran\s+en\s+el\s+padr[oó]n"
            r"|se\s+encuentra\s+en\s+la\s+lista\s+nominal"
            r"|\bser[aá]\s+v[aá]lida\s+hasta\b",
            re.I,
        ),
    ),
]

# Frases del portal que aparecen siempre, den lo que den los datos. Nunca
# deben influir en la clasificacion.
_RUIDO = re.compile(
    r"[¿?]\s*est[aá]\s+vigente\s+tu\s+credencial\s*\??"
    r"|s[oó]lo\s+con\s+las\s+credenciales\s+vigentes"
    r"|[¿?]\s*necesitas\s+ayuda\s*\??"
    r"|preguntas\s+frecuentes"
    r"|para\s+mayor\s+informaci[oó]n\s+llama"
    r"|servicio\s+por\s+cobrar"
    r"|centro\s+de\s+ayuda",
    re.I,
)

# Las fechas que el INE incluye son metadatos, no veredicto: se extraen aparte
# para que no ensucien ni la clasificacion ni el mensaje.
_FECHAS = re.compile(
    r"fecha\s+de\s+(actualizaci[oó]n(?:\s+de\s+la\s+informaci[oó]n)?|consulta)\s*:\s*(.+)",
    re.I,
)


@dataclass
class ResultadoParseado:
    estatus: EstatusLista
    veredicto: str
    campos: dict[str, str] = field(default_factory=dict)
    vigencia_hasta: str | None = None
    fecha_consulta: str | None = None
    fecha_actualizacion: str | None = None


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def _sopa(html: str) -> BeautifulSoup:
    sopa = BeautifulSoup(html, "lxml")
    for etiqueta in sopa(["script", "style", "noscript", "nav", "header", "footer"]):
        etiqueta.decompose()
    return sopa


def extraer_texto(html: str) -> str:
    return _limpiar(_sopa(html).get_text(separator=" ", strip=True))


def extraer_campos(sopa: BeautifulSoup) -> dict[str, str]:
    """Lee la tabla de datos de la credencial: <td><strong>k</strong></td><td>v</td>."""
    campos: dict[str, str] = {}
    for fila in sopa.select("table tr"):
        celdas = fila.find_all("td")
        if len(celdas) < 2:
            continue
        clave = _limpiar(celdas[0].get_text())
        valor = _limpiar(celdas[1].get_text())
        if clave and valor:
            campos[clave] = valor
    return campos


def extraer_veredicto(sopa: BeautifulSoup) -> str:
    """Aisla el bloque donde el INE dicta el resultado.

    El veredicto vive en los <h4> y <p class="lead"> que siguen a la tabla de
    datos. Restringirnos a esa zona es lo que evita que el encabezado fijo del
    portal contamine la clasificacion.
    """
    tabla = sopa.find("table")
    if tabla is not None:
        piezas = [
            _limpiar(el.get_text())
            for el in tabla.find_all_next(["h4", "p"])
            if el.name == "h4" or "lead" in (el.get("class") or [])
        ]
        piezas = [
            p
            for p in piezas
            if p and not _RUIDO.search(p) and not _FECHAS.match(p)
        ]
        if piezas:
            return " ".join(piezas)

    # Sin tabla (respuestas negativas podrian no traerla): caemos al texto
    # completo, pero descontando el boilerplate del portal.
    return _limpiar(_RUIDO.sub(" ", sopa.get_text(separator=" ", strip=True)))


def clasificar(texto: str) -> EstatusLista:
    limpio = _RUIDO.sub(" ", texto or "")
    for estatus, patron in _PATRONES:
        if patron.search(limpio):
            return estatus
    return EstatusLista.INDETERMINADO


def _vigencia(texto: str) -> str | None:
    """Extrae la fecha de vigencia, acotada al patron de fecha en espanol.

    Antes esto capturaba `(.+?)` hasta el final y se traia el pie de pagina
    del portal ("... de 2033 Preguntas Frecuentes").
    """
    m = re.search(
        r"ser[aá]\s+v[aá]lida\s+hasta\s+el\s+"
        r"(\d{1,2}\s+de\s+[a-záéíóúñ]+\s+del?\s+\d{4})",
        texto,
        re.I,
    )
    return _limpiar(m.group(1)) if m else None


def _extraer_fechas(sopa: BeautifulSoup) -> tuple[str | None, str | None]:
    """Devuelve (fecha_consulta, fecha_actualizacion)."""
    consulta = actualizacion = None
    for el in sopa.find_all("p"):
        m = _FECHAS.match(_limpiar(el.get_text()))
        if not m:
            continue
        etiqueta, valor = m.group(1).lower(), _limpiar(m.group(2))
        if etiqueta.startswith("consulta"):
            consulta = valor
        else:
            actualizacion = valor
    return consulta, actualizacion


def parsear(html: str) -> ResultadoParseado:
    sopa = _sopa(html)
    veredicto = extraer_veredicto(sopa)
    consulta, actualizacion = _extraer_fechas(sopa)
    return ResultadoParseado(
        estatus=clasificar(veredicto),
        veredicto=veredicto[:800],
        campos=extraer_campos(sopa),
        vigencia_hasta=_vigencia(veredicto),
        fecha_consulta=consulta,
        fecha_actualizacion=actualizacion,
    )


def parsear_resultado(html: str) -> tuple[EstatusLista, str]:
    """Forma corta, por compatibilidad con el codigo existente."""
    r = parsear(html)
    return r.estatus, r.veredicto
