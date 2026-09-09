import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def cliente():
    # El context manager dispara el lifespan, que es quien crea el INEClient.
    with TestClient(app) as c:
        yield c


def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_catalogo_entidades(cliente):
    r = cliente.get("/api/v1/catalogos/entidades")
    assert r.status_code == 200
    datos = r.json()
    assert len(datos) == 32
    assert datos[0] == {"clave": "01", "nombre": "AGUASCALIENTES"}


def test_validacion_local_ok(cliente):
    r = cliente.post("/api/v1/validacion/clave-elector", json={"clave_elector": "ABCDEF90010109H123"})
    assert r.status_code == 200
    assert r.json()["valida"] is True
    assert r.json()["entidad"] == "CIUDAD DE MEXICO"


def test_verificacion_sin_captcha_da_424(cliente):
    r = cliente.post(
        "/api/v1/verificacion",
        json={"modelo": "e", "cic": "123456789", "id_ciudadano": "987654321"},
    )
    assert r.status_code == 424


def test_verificacion_rechaza_campos_mal_formados(cliente):
    r = cliente.post(
        "/api/v1/verificacion",
        json={"modelo": "d", "cic": "12345678901234", "ocr": "1"},
    )
    assert r.status_code == 422


def test_verificacion_modelo_c_con_clave_invalida_no_sale_a_internet(cliente):
    r = cliente.post(
        "/api/v1/verificacion",
        json={
            "modelo": "c",
            "clave_elector": "XX",
            "numero_emision": "01",
            "ocr": "1234567890123",
            "captcha_token": "token-de-prueba",
        },
    )
    assert r.status_code == 422
