"""Consola de Verifine.

Uso tipico:

    python -m app.cli verificar --modelo e --cic 123456789 --id 987654321
    python -m app.cli verificar --archivo datos.txt
    python -m app.cli validar --clave ABCDEF90010109H123
    python -m app.cli entidades

`verificar` abre el navegador y espera a que marques el reCAPTCHA.
`validar` y `entidades` no salen a internet.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.config import get_settings
from app.core.clave_elector import analizar
from app.core.entidades import ENTIDADES
from app.core.validators import ErrorValidacion
from app.models.enums import EstatusLista
from app.models.schemas import (
    ConsultaModeloC,
    ConsultaModeloD,
    ConsultaModeloEFGH,
    ConsultaReporte,
)

consola = Console()

# Como se pinta cada veredicto.
_ESTILO: dict[EstatusLista, tuple[str, str]] = {
    EstatusLista.VIGENTE: ("green", "VIGENTE"),
    EstatusLista.NO_VIGENTE: ("red", "NO VIGENTE"),
    EstatusLista.NO_ENCONTRADO: ("red", "NO ENCONTRADO"),
    EstatusLista.ROBO_EXTRAVIO: ("red", "ROBO O EXTRAVIO"),
    EstatusLista.DATOS_NO_COINCIDEN: ("yellow", "LOS DATOS NO COINCIDEN"),
    EstatusLista.INDETERMINADO: ("yellow", "INDETERMINADO"),
}


def _leer_archivo(ruta: str) -> list[str]:
    with open(ruta, encoding="utf-8") as fh:
        return fh.read().split()


def _construir_consulta(args):
    """Arma la consulta del modelo correspondiente a partir de los argumentos."""
    if args.archivo:
        valores = _leer_archivo(args.archivo)
        if args.modelo == "e":
            if len(valores) != 2:
                raise SystemExit(
                    f"El archivo debe traer 2 valores (CIC e identificador), trae {len(valores)}"
                )
            return ConsultaModeloEFGH(cic=valores[0], id_ciudadano=valores[1])
        raise SystemExit("--archivo solo esta soportado para el modelo e por ahora")

    modelo = args.modelo
    if modelo == "e":
        if not (args.cic and args.id):
            raise SystemExit("El modelo e necesita --cic y --id")
        return ConsultaModeloEFGH(cic=args.cic, id_ciudadano=args.id)
    if modelo == "d":
        if not (args.cic and args.ocr):
            raise SystemExit("El modelo d necesita --cic y --ocr")
        return ConsultaModeloD(cic=args.cic, ocr=args.ocr)
    if modelo == "c":
        if not (args.clave and args.emision and args.ocr):
            raise SystemExit("El modelo c necesita --clave, --emision y --ocr")
        return ConsultaModeloC(
            clave_elector=args.clave, numero_emision=args.emision, ocr=args.ocr
        )
    if modelo == "r":
        if not args.reporte:
            raise SystemExit("El modelo r necesita --reporte")
        return ConsultaReporte(numero_reporte=args.reporte)
    raise SystemExit(f"Modelo desconocido: {modelo}")


def _pintar_resultado(resultado, momento: str) -> None:
    color, etiqueta = _ESTILO[resultado.estatus]

    cuerpo = Text()
    cuerpo.append(etiqueta, style=f"bold {color}")
    if resultado.vigencia_hasta:
        cuerpo.append(f"\nValida hasta el {resultado.vigencia_hasta}", style="bold")
    cuerpo.append(f"\n\n{resultado.veredicto}", style="dim")

    consola.print()
    consola.print(
        Panel(cuerpo, title="Veredicto del INE", border_style=color, padding=(1, 2))
    )

    if resultado.campos:
        tabla = Table(show_header=True, header_style="bold", border_style="dim")
        tabla.add_column("Dato")
        tabla.add_column("Valor")
        for clave, valor in resultado.campos.items():
            tabla.add_row(clave, valor)
        consola.print(tabla)

    pie = []
    if resultado.fecha_consulta:
        pie.append(f"Consulta INE: {resultado.fecha_consulta}")
    if resultado.fecha_actualizacion:
        pie.append(f"Padron actualizado: {resultado.fecha_actualizacion}")
    pie.append(f"Registrado por Verifine: {momento}")
    consola.print("  ".join(pie), style="dim")


def _pintar_clave(r) -> None:
    color = "green" if r.valida else "red"
    titulo = "ESTRUCTURA VALIDA" if r.valida else "ESTRUCTURA INVALIDA"
    consola.print()
    consola.print(
        Panel(
            Text(titulo, style=f"bold {color}"),
            title=f"Clave {r.clave}",
            border_style=color,
        )
    )
    if r.errores:
        for e in r.errores:
            consola.print(f"  - {e}", style="red")
        return

    tabla = Table(show_header=True, header_style="bold", border_style="dim")
    tabla.add_column("Componente")
    tabla.add_column("Valor")
    tabla.add_row("Letras de nombre", r.consonantes)
    tabla.add_row("Fecha de nacimiento", str(r.fecha_nacimiento))
    tabla.add_row("Entidad", f"{r.clave_entidad} - {r.entidad}")
    tabla.add_row("Sexo", r.sexo)
    tabla.add_row("Homoclave", r.homoclave)
    tabla.add_row("Digito de disponibilidad", r.digito_disponibilidad)
    tabla.add_row("Edad", f"{r.edad} anios")
    consola.print(tabla)
    consola.print(
        "Ojo: esto valida la forma, no que la clave exista en el padron.",
        style="dim yellow",
    )


async def _verificar(args) -> int:
    from app.services.navegador import NavegadorINE

    try:
        consulta = _construir_consulta(args)
    except ErrorValidacion as exc:
        consola.print(f"[red]Dato invalido:[/red] {exc}")
        return 2

    settings = get_settings()
    espera = settings.navegador_timeout_captcha
    consola.print(
        f"[dim]Modelo {consulta.modelo.value} - se abrira el navegador; "
        f"marca el reCAPTCHA (tienes {espera:.0f}s)[/dim]"
    )

    def avisar(m: str) -> None:
        if not args.json:
            consola.print(f"  [dim]{m}[/dim]")

    nav = NavegadorINE(settings)
    try:
        resultado, momento = await nav.consultar_asistido(
            consulta, guardar_html=args.guardar_html, notificar=avisar
        )
    except Exception as exc:
        consola.print(f"[red]Fallo la consulta:[/red] {type(exc).__name__}: {exc}")
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "estatus": resultado.estatus.value,
                    "veredicto": resultado.veredicto,
                    "vigencia_hasta": resultado.vigencia_hasta,
                    "fecha_consulta": resultado.fecha_consulta,
                    "fecha_actualizacion": resultado.fecha_actualizacion,
                    "campos": resultado.campos,
                    "consultado_en": momento,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _pintar_resultado(resultado, momento)

    return 0 if resultado.estatus is EstatusLista.VIGENTE else 3


def _validar(args) -> int:
    clave = args.clave
    if args.archivo and not clave:
        clave = _leer_archivo(args.archivo)[0]
    if not clave:
        raise SystemExit("Falta --clave")

    r = analizar(clave)
    if args.json:
        print(json.dumps(r.__dict__, ensure_ascii=False, indent=2, default=str))
    else:
        _pintar_clave(r)
    return 0 if r.valida else 3


def _mostrar(args) -> int:
    """Renderiza un resultado.html ya guardado, sin volver a consultar.

    Util para revisar una consulta pasada y para ajustar el parser sin tener
    que resolver otro captcha.
    """
    from app.services.parser import parsear

    with open(args.html, encoding="utf-8") as fh:
        resultado = parsear(fh.read())

    if args.json:
        print(
            json.dumps(
                {
                    "estatus": resultado.estatus.value,
                    "veredicto": resultado.veredicto,
                    "vigencia_hasta": resultado.vigencia_hasta,
                    "fecha_consulta": resultado.fecha_consulta,
                    "fecha_actualizacion": resultado.fecha_actualizacion,
                    "campos": resultado.campos,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _pintar_resultado(resultado, f"(desde {args.html})")
    return 0 if resultado.estatus is EstatusLista.VIGENTE else 3


def _entidades(args) -> int:
    if args.json:
        print(json.dumps(ENTIDADES, ensure_ascii=False, indent=2))
        return 0
    tabla = Table(title="Entidades federativas (clave INE)", header_style="bold")
    tabla.add_column("Clave")
    tabla.add_column("Entidad")
    for clave, nombre in sorted(ENTIDADES.items()):
        tabla.add_row(clave, nombre)
    consola.print(tabla)
    return 0


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="verifine",
        description="Valida credenciales para votar (INE) desde la consola.",
    )
    p.add_argument("--json", action="store_true", help="Salida en JSON en vez de tablas")
    sub = p.add_subparsers(dest="comando", required=True)

    v = sub.add_parser("verificar", help="Consulta al INE (abre el navegador)")
    v.add_argument("--modelo", choices=["c", "d", "e", "r"], default="e")
    v.add_argument("--cic")
    v.add_argument("--id", help="Identificador del ciudadano (modelo e)")
    v.add_argument("--ocr")
    v.add_argument("--clave", help="Clave de elector (modelo c)")
    v.add_argument("--emision", help="Numero de emision (modelo c)")
    v.add_argument("--reporte", help="Numero de reporte (modelo r)")
    v.add_argument("--archivo", help="Archivo con los valores, uno por linea")
    v.add_argument("--guardar-html", dest="guardar_html", help="Vuelca el HTML crudo aqui")

    d = sub.add_parser("validar", help="Analiza una clave de elector en local")
    d.add_argument("--clave")
    d.add_argument("--archivo")

    m = sub.add_parser("mostrar", help="Renderiza un resultado.html ya guardado")
    m.add_argument("--html", required=True, help="Ruta al HTML de una consulta previa")

    sub.add_parser("entidades", help="Catalogo de entidades federativas")

    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.comando == "verificar":
        return asyncio.run(_verificar(args))
    if args.comando == "validar":
        return _validar(args)
    if args.comando == "mostrar":
        return _mostrar(args)
    if args.comando == "entidades":
        return _entidades(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
