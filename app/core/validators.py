"""Validaciones de forma para los campos numericos que pide el INE."""

from __future__ import annotations

import re


class ErrorValidacion(ValueError):
    """Un campo no cumple el formato que exige el formulario del INE."""


def _solo_digitos(valor: str, *, campo: str, longitud: int, rellenar: bool = True) -> str:
    limpio = re.sub(r"[\s\-]", "", valor or "")

    if not limpio:
        raise ErrorValidacion(f"{campo} es obligatorio")

    if not limpio.isdigit():
        raise ErrorValidacion(f"{campo} solo admite digitos")

    if rellenar and len(limpio) < longitud:
        # El formulario del INE exige los ceros a la izquierda; los agregamos
        # nosotros para que el usuario no tenga que contarlos.
        limpio = limpio.zfill(longitud)

    if len(limpio) != longitud:
        raise ErrorValidacion(f"{campo} debe tener {longitud} digitos, tiene {len(limpio)}")

    return limpio


def validar_cic(valor: str) -> str:
    """CIC (Codigo de Identificacion de Credencial): 9 digitos."""
    return _solo_digitos(valor, campo="El CIC", longitud=9)


def validar_id_ciudadano(valor: str) -> str:
    """Identificador del ciudadano, modelos E/F/G/H: 9 digitos."""
    return _solo_digitos(valor, campo="El identificador del ciudadano", longitud=9)


def validar_ocr(valor: str) -> str:
    """OCR: 13 digitos, con ceros a la izquierda."""
    return _solo_digitos(valor, campo="El OCR", longitud=13)


def validar_numero_emision(valor: str) -> str:
    """Numero de emision: 2 digitos."""
    return _solo_digitos(valor, campo="El numero de emision", longitud=2)


def validar_numero_reporte(valor: str) -> str:
    """Numero de reporte de robo o extravio: 18 digitos."""
    return _solo_digitos(valor, campo="El numero de reporte", longitud=18)
