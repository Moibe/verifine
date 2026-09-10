"""Esquemas de entrada y salida de la API."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

from app.core import validators as v
from app.core.clave_elector import normalizar as normalizar_clave
from app.models.enums import EstatusLista, ModeloCredencial


# --------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------
class _Base(BaseModel):
    captcha_token: str | None = Field(
        default=None,
        description=(
            "Token `g-recaptcha-response` obtenido al resolver el reCAPTCHA del "
            "INE. Obligatorio para consultar; no se requiere para /validacion."
        ),
    )


class ConsultaModeloC(_Base):
    """Credenciales modelo A, B y C: clave de elector + emision + OCR."""

    modelo: Literal[ModeloCredencial.C] = ModeloCredencial.C
    clave_elector: str = Field(..., description="18 caracteres")
    numero_emision: str = Field(..., description="2 digitos")
    ocr: str = Field(..., description="13 digitos, con ceros a la izquierda")

    @field_validator("clave_elector")
    @classmethod
    def _clave(cls, valor: str) -> str:
        return normalizar_clave(valor)

    @field_validator("numero_emision")
    @classmethod
    def _emision(cls, valor: str) -> str:
        return v.validar_numero_emision(valor)

    @field_validator("ocr")
    @classmethod
    def _ocr(cls, valor: str) -> str:
        return v.validar_ocr(valor)


class ConsultaModeloD(_Base):
    """Credencial modelo D: CIC + OCR."""

    modelo: Literal[ModeloCredencial.D] = ModeloCredencial.D
    cic: str = Field(..., description="9 digitos")
    ocr: str = Field(..., description="13 digitos")

    @field_validator("cic")
    @classmethod
    def _cic(cls, valor: str) -> str:
        return v.validar_cic(valor)

    @field_validator("ocr")
    @classmethod
    def _ocr(cls, valor: str) -> str:
        return v.validar_ocr(valor)


class ConsultaModeloEFGH(_Base):
    """Credenciales modelo E, F, G y H: CIC + identificador del ciudadano."""

    modelo: Literal[ModeloCredencial.E] = ModeloCredencial.E
    cic: str = Field(..., description="9 digitos")
    id_ciudadano: str = Field(..., description="9 digitos")

    @field_validator("cic")
    @classmethod
    def _cic(cls, valor: str) -> str:
        return v.validar_cic(valor)

    @field_validator("id_ciudadano")
    @classmethod
    def _idc(cls, valor: str) -> str:
        return v.validar_id_ciudadano(valor)


class ConsultaReporte(_Base):
    """Consulta por numero de reporte de robo o extravio."""

    modelo: Literal[ModeloCredencial.R] = ModeloCredencial.R
    numero_reporte: str = Field(..., description="18 digitos")

    @field_validator("numero_reporte")
    @classmethod
    def _reporte(cls, valor: str) -> str:
        return v.validar_numero_reporte(valor)


Consulta = Annotated[
    Union[ConsultaModeloC, ConsultaModeloD, ConsultaModeloEFGH, ConsultaReporte],
    Field(discriminator="modelo"),
]


class ValidacionClaveRequest(BaseModel):
    clave_elector: str


# --------------------------------------------------------------------------
# Salida
# --------------------------------------------------------------------------
class ClaveElectorOut(BaseModel):
    clave: str
    valida: bool
    errores: list[str] = []
    consonantes: str | None = None
    fecha_nacimiento: date | None = None
    clave_entidad: str | None = None
    entidad: str | None = None
    sexo: str | None = None
    homoclave: str | None = None
    digito_disponibilidad: str | None = None
    edad: int | None = None
    mayor_de_edad: bool | None = None


class ResultadoConsulta(BaseModel):
    modelo: ModeloCredencial
    estatus: EstatusLista
    encontrado: bool
    mensaje: str = Field(description="Veredicto tal como lo redacto el INE")
    consultado_en: str = Field(description="Marca de tiempo ISO-8601 de nuestra consulta")
    campos: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Datos de la credencial que el INE devuelve en su tabla: CIC, clave "
            "de elector, numero de emision, distrito federal y local, OCR, anio "
            "de registro y de emision."
        ),
    )
    vigencia_hasta: str | None = Field(
        default=None, description="Fecha hasta la que el INE declara valida la credencial"
    )
    fecha_consulta: str | None = Field(
        default=None, description="Fecha de consulta segun el propio INE"
    )
    fecha_actualizacion: str | None = Field(
        default=None, description="Ultima actualizacion del padron segun el INE"
    )
    analisis_clave: ClaveElectorOut | None = Field(
        default=None,
        description="Solo para modelo C, donde hay clave de elector que analizar",
    )


class Entidad(BaseModel):
    clave: str
    nombre: str
