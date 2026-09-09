from datetime import date

from app.core.clave_elector import analizar, normalizar


def test_normaliza_espacios_y_minusculas():
    assert normalizar(" abcdef 900101 09 h 123 ") == "ABCDEF90010109H123"


def test_clave_bien_formada_se_descompone():
    # ABCDEF | 900101 | 09 | H | 12 | 3
    r = analizar("ABCDEF900101 09H123")
    assert r.valida, r.errores
    assert r.consonantes == "ABCDEF"
    assert r.fecha_nacimiento == date(1990, 1, 1)
    assert r.clave_entidad == "09"
    assert r.entidad == "CIUDAD DE MEXICO"
    assert r.sexo == "H"
    assert r.homoclave == "12"
    assert r.digito_disponibilidad == "3"
    assert r.mayor_de_edad is True


def test_longitud_incorrecta():
    r = analizar("ABCDEF900101")
    assert not r.valida
    assert "18 caracteres" in r.errores[0]


def test_entidad_inexistente():
    r = analizar("ABCDEF90010199H123")
    assert not r.valida
    assert any("entidad" in e for e in r.errores)


def test_formato_invalido_sexo():
    r = analizar("ABCDEF90010109X123")
    assert not r.valida


def test_fecha_imposible():
    r = analizar("ABCDEF901301 09H123")
    assert not r.valida
    assert any("fecha" in e for e in r.errores)


def test_clave_vacia():
    r = analizar("")
    assert not r.valida
