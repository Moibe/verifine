import pytest

from app.core.validators import (
    ErrorValidacion,
    validar_cic,
    validar_numero_emision,
    validar_ocr,
)


def test_cic_valido():
    assert validar_cic("123456789") == "123456789"


def test_cic_rellena_ceros_a_la_izquierda():
    assert validar_cic("6789") == "000006789"


def test_ocr_trece_digitos():
    assert validar_ocr("1234567890123") == "1234567890123"


def test_ocr_demasiado_largo():
    with pytest.raises(ErrorValidacion):
        validar_ocr("12345678901234")


def test_no_admite_letras():
    with pytest.raises(ErrorValidacion):
        validar_cic("12345678A")


def test_campo_vacio():
    with pytest.raises(ErrorValidacion):
        validar_numero_emision("")
