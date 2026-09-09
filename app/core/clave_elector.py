"""Analisis estructural de la clave de elector (18 caracteres).

Estructura documentada por el INE:

    posiciones  1-6   6 letras derivadas de apellidos y nombre
    posiciones  7-12  fecha de nacimiento AAMMDD
    posiciones 13-14  clave de la entidad federativa de nacimiento (01-32)
    posicion   15     sexo (H / M)
    posiciones 16-17  homoclave asignada por el INE
    posicion   18     digito de disponibilidad

Ojo: esto valida la FORMA de la clave, no que exista en el padron. Solo el
INE puede confirmar lo segundo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.core.entidades import nombre_entidad

LONGITUD = 18
_PATRON = re.compile(r"^[A-Z]{6}\d{6}\d{2}[HM]\d{3}$")


@dataclass
class ClaveElectorAnalizada:
    clave: str
    valida: bool
    errores: list[str] = field(default_factory=list)
    consonantes: str | None = None
    fecha_nacimiento: date | None = None
    clave_entidad: str | None = None
    entidad: str | None = None
    sexo: str | None = None
    homoclave: str | None = None
    digito_disponibilidad: str | None = None
    edad: int | None = None
    mayor_de_edad: bool | None = None


def normalizar(clave: str) -> str:
    """Quita espacios y guiones, y pasa a mayusculas."""
    return re.sub(r"[\s\-]", "", clave or "").upper()


def _parsear_fecha(bloque: str) -> tuple[date | None, str | None]:
    """AAMMDD -> date. El siglo se infiere: si el ano de 2 digitos cae en el
    futuro respecto a hoy, pertenece al siglo XX."""
    try:
        aa, mm, dd = int(bloque[0:2]), int(bloque[2:4]), int(bloque[4:6])
    except ValueError:
        return None, "La fecha de nacimiento no es numerica"

    hoy = date.today()
    anio = 2000 + aa
    if anio > hoy.year:
        anio = 1900 + aa

    try:
        return date(anio, mm, dd), None
    except ValueError:
        return None, f"La fecha de nacimiento '{bloque}' no es una fecha valida"


def _calcular_edad(nacimiento: date, referencia: date | None = None) -> int:
    hoy = referencia or date.today()
    return hoy.year - nacimiento.year - (
        (hoy.month, hoy.day) < (nacimiento.month, nacimiento.day)
    )


def analizar(clave: str) -> ClaveElectorAnalizada:
    clave = normalizar(clave)
    errores: list[str] = []

    if not clave:
        return ClaveElectorAnalizada(clave="", valida=False, errores=["La clave de elector es obligatoria"])

    if len(clave) != LONGITUD:
        errores.append(f"La clave debe tener {LONGITUD} caracteres, tiene {len(clave)}")
        return ClaveElectorAnalizada(clave=clave, valida=False, errores=errores)

    if not _PATRON.match(clave):
        errores.append(
            "La clave no cumple el formato esperado "
            "(6 letras + 6 digitos de fecha + 2 digitos de entidad + H/M + 3 digitos)"
        )
        return ClaveElectorAnalizada(clave=clave, valida=False, errores=errores)

    consonantes = clave[0:6]
    fecha, err_fecha = _parsear_fecha(clave[6:12])
    if err_fecha:
        errores.append(err_fecha)

    clave_entidad = clave[12:14]
    entidad = nombre_entidad(clave_entidad)
    if entidad is None:
        errores.append(f"La clave de entidad '{clave_entidad}' no existe (debe estar entre 01 y 32)")

    sexo = clave[14]
    homoclave = clave[15:17]
    digito = clave[17]

    edad = _calcular_edad(fecha) if fecha else None
    if edad is not None and edad < 18:
        errores.append(f"La fecha de nacimiento implica {edad} anios: no alcanza la edad para votar")

    return ClaveElectorAnalizada(
        clave=clave,
        valida=not errores,
        errores=errores,
        consonantes=consonantes,
        fecha_nacimiento=fecha,
        clave_entidad=clave_entidad,
        entidad=entidad,
        sexo=sexo,
        homoclave=homoclave,
        digito_disponibilidad=digito,
        edad=edad,
        mayor_de_edad=(edad >= 18) if edad is not None else None,
    )
