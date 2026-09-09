from app.models.enums import EstatusLista
from app.services.parser import clasificar, extraer_texto, parsear_resultado


def test_extraer_texto_quita_scripts():
    html = "<html><script>var a=1;</script><p>Hola  mundo</p></html>"
    assert extraer_texto(html) == "Hola mundo"


def test_clasifica_vigente():
    assert clasificar("El ciudadano se encuentra en la Lista Nominal") is EstatusLista.VIGENTE


def test_clasifica_no_encontrado():
    assert clasificar("El registro no se encuentra") is EstatusLista.NO_ENCONTRADO


def test_clasifica_robo():
    assert clasificar("Credencial reportada como robada") is EstatusLista.ROBO_EXTRAVIO


def test_indeterminado_conserva_texto():
    estatus, mensaje = parsear_resultado("<p>Respuesta inesperada del portal</p>")
    assert estatus is EstatusLista.INDETERMINADO
    assert "Respuesta inesperada" in mensaje


def test_vigente_no_se_confunde_con_ciudadano():
    # "ciudadano se encuentra" contiene la subcadena "no se encuentra".
    assert clasificar("El ciudadano se encuentra en la Lista Nominal") is EstatusLista.VIGENTE
