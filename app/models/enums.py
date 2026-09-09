from enum import Enum


class ModeloCredencial(str, Enum):
    """Valores del campo oculto `modelo` en los formularios del INE."""

    C = "c"  # Modelos A, B y C: clave de elector + numero de emision + OCR
    D = "d"  # Modelo D: CIC + OCR
    E = "e"  # Modelos E, F, G, H, I y J: CIC + identificador del ciudadano
    R = "r"  # Reporte de robo o extravio


class EstatusLista(str, Enum):
    """Resultado normalizado de la consulta a la Lista Nominal."""

    VIGENTE = "vigente"
    NO_VIGENTE = "no_vigente"
    NO_ENCONTRADO = "no_encontrado"
    ROBO_EXTRAVIO = "robo_extravio"
    DATOS_NO_COINCIDEN = "datos_no_coinciden"
    INDETERMINADO = "indeterminado"


class Sexo(str, Enum):
    H = "H"
    M = "M"
