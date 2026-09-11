"""Automatizacion asistida del formulario del INE con Playwright.

Que automatiza y que no
-----------------------
Automatiza: abrir la pagina, ubicar el formulario del modelo correcto, capturar
todos los campos, enviar, esperar el resultado y parsearlo.

No automatiza: marcar el reCAPTCHA. Ese control existe para distinguir a una
persona de un programa; el navegador se abre CON interfaz y espera a que una
persona lo marque. Por eso `headless` no es configurable: en headless nadie
podria resolverlo, y el intento seria detectado de todos modos.

El contexto del navegador es persistente (`navegador_perfil_dir`), asi que las
cookies de sesion sobreviven entre consultas y no hay que empezar de cero cada
vez.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.models.enums import EstatusLista, ModeloCredencial
from app.services.ine_client import ErrorINE
from app.services.parser import ResultadoParseado, parsear


class PlaywrightNoInstalado(ErrorINE):
    """Falta la dependencia opcional de Playwright."""


class CaptchaNoResuelto(ErrorINE):
    """Nadie marco el reCAPTCHA dentro del tiempo de espera."""


class ErrorDriver(ErrorINE):
    """El driver de Playwright (un proceso node) murio al arrancar.

    Suele ser transitorio. En equipos corporativos la causa habitual es un
    antivirus o EDR que mata `node.exe` al detectar que lanza un navegador.
    """


# Firmas del driver cayendose, que no dependen del idioma del sistema.
_FALLOS_DE_DRIVER = (
    "connection closed while reading from the driver",
    "connection closed",
    "browser has been closed",
    "target closed",
    "driver",
)


def _es_fallo_de_driver(exc: BaseException) -> bool:
    """Distingue un driver caido de un error de nuestro flujo.

    Solo los primeros valen la pena reintentar: los segundos volverian a
    fallar igual.
    """
    mensaje = str(exc).lower()
    return any(firma in mensaje for firma in _FALLOS_DE_DRIVER)


# Cada modelo vive en su propio <form> dentro de la misma pagina.
_FORMULARIOS: dict[ModeloCredencial, dict] = {
    ModeloCredencial.C: {
        "form": "#formC",
        "captcha": "#recaptchaC",
        "campos": ("claveElector", "numeroEmision", "ocr"),
    },
    ModeloCredencial.D: {
        "form": "#formD",
        "captcha": "#recaptchaD",
        "campos": ("cic", "ocr"),
    },
    ModeloCredencial.E: {
        "form": "#formEFGH",
        "captcha": "#recaptchaEFGH",
        "campos": ("cic", "idCiudadano"),
    },
    ModeloCredencial.R: {
        "form": "#formR",
        "captcha": "#recaptchaR",
        "campos": ("numeroReporteRoboExtravio",),
    },
}


def _valores_formulario(consulta) -> dict[str, str]:
    """Reusa el mapeo de names del cliente HTTP, sin el token de captcha."""
    from app.services.ine_client import construir_payload

    datos = construir_payload(consulta)
    datos.pop("g-recaptcha-response", None)
    datos.pop("modelo", None)
    return datos


class NavegadorINE:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def consultar_asistido(
        self,
        consulta,
        *,
        guardar_html: str | None = None,
        notificar=None,
    ) -> tuple[ResultadoParseado, str]:
        """Ejecuta el flujo asistido.

        guardar_html: ruta donde volcar el HTML crudo del resultado. Sirve para
        ajustar el parser contra una respuesta real del INE.
        notificar: callable(str) opcional para reportar avance al usuario.
        """
        avisar = notificar or (lambda _m: None)
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise PlaywrightNoInstalado(
                "Playwright no esta instalado. Ejecuta:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            ) from exc

        from playwright.async_api import TimeoutError as PWTimeout

        modelo = ModeloCredencial(consulta.modelo)
        cfg = _FORMULARIOS[modelo]
        valores = _valores_formulario(consulta)

        intentos = max(1, self._settings.navegador_reintentos)
        ultimo: BaseException | None = None

        for intento in range(1, intentos + 1):
            # Registra si ya le pedimos a la persona que marque el captcha.
            # A partir de ese punto no se reintenta: seria reabrir el
            # navegador y obligarla a marcarlo otra vez sin explicacion.
            estado = {"pidio_captcha": False}
            try:
                return await self._flujo(
                    async_playwright, PWTimeout, cfg, valores, guardar_html, avisar, estado
                )
            except CaptchaNoResuelto:
                raise
            except Exception as exc:
                ultimo = exc
                if estado["pidio_captcha"] or not _es_fallo_de_driver(exc) or intento >= intentos:
                    break
                avisar(
                    f"El navegador no arranco ({type(exc).__name__}). "
                    f"Reintento {intento + 1} de {intentos}."
                )

        assert ultimo is not None
        if _es_fallo_de_driver(ultimo):
            raise ErrorDriver(
                f"El driver de Playwright murio al arrancar ({ultimo}). "
                f"Lo intente {intentos} vez/veces.\n\n"
                "En equipos corporativos la causa mas comun es un antivirus o "
                "EDR que mata node.exe cuando intenta lanzar un navegador. "
                "Suele ser intermitente: volver a correr el comando funciona.\n\n"
                "Para revisar tu entorno:  python -m app.cli diagnostico"
            ) from ultimo
        raise ultimo

    async def _flujo(
        self, async_playwright, PWTimeout, cfg, valores, guardar_html, avisar, estado
    ) -> tuple[ResultadoParseado, str]:
        """Un intento completo: abrir, capturar, esperar el captcha, enviar."""
        async with async_playwright() as pw:
            contexto = await pw.chromium.launch_persistent_context(
                self._settings.navegador_perfil_dir,
                headless=False,  # deliberado: el captcha lo marca una persona
                locale="es-MX",
                viewport={"width": 1280, "height": 900},
            )
            try:
                pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
                avisar(f"Abriendo {self._settings.ine_base_url}")
                await pagina.goto(self._settings.ine_base_url, wait_until="domcontentloaded")

                # 1. Capturar los campos del formulario que corresponde.
                for name in cfg["campos"]:
                    selector = f'{cfg["form"]} input[name="{name}"]'
                    await pagina.wait_for_selector(selector, timeout=15_000)
                    await pagina.fill(selector, valores[name])
                    avisar(f"Campo {name} capturado")

                # 2. Traer el captcha a la vista y esperar a la persona.
                await pagina.locator(cfg["captcha"]).scroll_into_view_if_needed()
                token_llenado = (
                    f'{cfg["captcha"]} textarea[name="g-recaptcha-response"]'
                )
                # Diagnostico: si el textarea no existe dentro del div del
                # widget, la espera de abajo nunca terminaria. Mejor decirlo.
                existe = await pagina.evaluate(
                    "sel => !!document.querySelector(sel)", token_llenado
                )
                avisar(
                    f"Widget de captcha listo (textarea presente: {existe}). "
                    "Marca el reCAPTCHA en la ventana del navegador."
                )
                # Desde aqui ya hay una persona mirando el navegador: pase lo
                # que pase, no se reintenta por detras.
                estado["pidio_captcha"] = True
                try:
                    await pagina.wait_for_function(
                        "sel => { const t = document.querySelector(sel);"
                        " return !!t && t.value.length > 0; }",
                        arg=token_llenado,
                        timeout=self._settings.navegador_timeout_captcha * 1000,
                    )
                except PWTimeout as exc:
                    raise CaptchaNoResuelto(
                        "Nadie marco el reCAPTCHA en "
                        f"{self._settings.navegador_timeout_captcha:.0f} s."
                    ) from exc

                # 3. Enviar y esperar la pagina de resultado.
                async with pagina.expect_navigation(wait_until="domcontentloaded", timeout=60_000):
                    await pagina.click(f'{cfg["form"]} button[type="submit"]')

                html = await pagina.content()
                avisar(f"Resultado recibido de {pagina.url}")

                if guardar_html:
                    import pathlib

                    pathlib.Path(guardar_html).write_text(html, encoding="utf-8")
                    avisar(f"HTML crudo guardado en {guardar_html}")
            finally:
                await contexto.close()

        return parsear(html), datetime.now(timezone.utc).isoformat()
