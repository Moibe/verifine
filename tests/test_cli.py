"""Pruebas de la consola.

Ninguna sale a internet: se apoyan en el fixture de la respuesta real y en la
validacion local.
"""

import json
import pathlib

import pytest

from app.cli import main

FIXTURE = str(pathlib.Path(__file__).parent / "fixtures" / "resultado_vigente.html")


# --------------------------------------------------------------------------
# mostrar
# --------------------------------------------------------------------------
def test_mostrar_pinta_el_veredicto(capsys):
    codigo = main(["mostrar", "--html", FIXTURE])
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "VIGENTE" in salida
    assert "31 de diciembre de 2033" in salida
    # La tabla de datos tambien debe aparecer.
    assert "Clave de elector" in salida
    assert "Distrito Federal" in salida


def test_mostrar_en_json_es_json_valido(capsys):
    main(["--json", "mostrar", "--html", FIXTURE])
    datos = json.loads(capsys.readouterr().out)
    assert datos["estatus"] == "vigente"
    assert datos["vigencia_hasta"] == "31 de diciembre de 2033"
    assert datos["campos"]["Año de registro"] == "2012"
    # El JSON no debe traer el ruido del portal.
    assert "Preguntas Frecuentes" not in datos["veredicto"]


# --------------------------------------------------------------------------
# validar
# --------------------------------------------------------------------------
def test_validar_clave_correcta(capsys):
    codigo = main(["validar", "--clave", "ABCDEF90010109H123"])
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "ESTRUCTURA VALIDA" in salida
    assert "CIUDAD DE MEXICO" in salida


def test_validar_clave_incorrecta_sale_con_3(capsys):
    codigo = main(["validar", "--clave", "XX"])
    assert codigo == 3
    assert "ESTRUCTURA INVALIDA" in capsys.readouterr().out


def test_validar_en_json(capsys):
    main(["--json", "validar", "--clave", "ABCDEF90010109H123"])
    datos = json.loads(capsys.readouterr().out)
    assert datos["valida"] is True
    assert datos["entidad"] == "CIUDAD DE MEXICO"


# --------------------------------------------------------------------------
# entidades
# --------------------------------------------------------------------------
def test_entidades_json_trae_las_32(capsys):
    main(["--json", "entidades"])
    datos = json.loads(capsys.readouterr().out)
    assert len(datos) == 32
    assert datos["09"] == "CIUDAD DE MEXICO"


# --------------------------------------------------------------------------
# Validacion de argumentos: debe fallar ANTES de abrir el navegador
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "argv",
    [
        ["verificar", "--modelo", "e", "--cic", "123456789"],  # falta --id
        ["verificar", "--modelo", "d", "--cic", "123456789"],  # falta --ocr
        ["verificar", "--modelo", "c", "--clave", "ABCDEF90010109H123"],  # falta emision/ocr
        ["verificar", "--modelo", "r"],  # falta --reporte
    ],
)
def test_faltan_argumentos_no_abre_navegador(argv):
    """Si falta un dato, debe abortar sin lanzar Chromium."""
    with pytest.raises(SystemExit):
        main(argv)


def test_archivo_con_numero_equivocado_de_valores(tmp_path):
    ruta = tmp_path / "datos.txt"
    ruta.write_text("111111111\n", encoding="utf-8")  # falta el segundo
    with pytest.raises(SystemExit):
        main(["verificar", "--modelo", "e", "--archivo", str(ruta)])


def test_archivo_valido_construye_la_consulta(tmp_path):
    """El archivo se lee bien; solo comprobamos la construccion, sin consultar."""
    from app.cli import _construir_consulta, construir_parser

    ruta = tmp_path / "datos.txt"
    ruta.write_text("111111111\n222222222\n", encoding="utf-8")
    args = construir_parser().parse_args(
        ["verificar", "--modelo", "e", "--archivo", str(ruta)]
    )
    consulta = _construir_consulta(args)
    assert consulta.cic == "111111111"
    assert consulta.id_ciudadano == "222222222"
