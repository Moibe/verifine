# Verifine

API en FastAPI para validar credenciales para votar (INE) contra el servicio
publico de Lista Nominal: <https://listanominal.ine.mx/scpln/>

La API hace dos cosas distintas, y conviene no confundirlas:

| | Que hace | Necesita internet | Necesita captcha |
|---|---|---|---|
| `/api/v1/validacion/*` | Valida la **estructura** de los datos | No | No |
| `/api/v1/verificacion` | Consulta la **Lista Nominal** del INE | Si | Si (token) |
| `/api/v1/verificacion/asistida` | Igual, pero abriendo un navegador | Si | Si (un clic) |

Una clave estructuralmente valida puede perfectamente no existir en el padron.
Solo el INE confirma lo segundo.

## El reCAPTCHA: lo que hay que saber antes de integrar

Los cuatro formularios del INE estan protegidos con **Google reCAPTCHA v2**
(sitekey `6LdAe1sUAAAAACrdhVFHK5KmZ5TA8ZJ0iWQ6i64b`) y el sitio esta detras de
**Cloudflare**, que interpone challenges a clientes automatizados.

Este proyecto **no evade ninguno de los dos**. `/api/v1/verificacion` exige un
campo `captcha_token` con el valor `g-recaptcha-response` ya resuelto, y lo
reenvia al INE. Resolver ese captcha es responsabilidad de quien llama:
normalmente una persona en el frontend.

Consecuencia practica: **no hay verificacion desatendida ni por lotes**. Cada
consulta necesita un captcha nuevo resuelto por una persona.

Si Cloudflare bloquea la peticion, la API responde `502` diciendolo, en vez de
inventar un resultado.

## Modo asistido: automatizar todo menos el clic

`/api/v1/verificacion/asistida` es la via comoda. Abre Chromium **con
interfaz**, ubica el formulario del modelo correcto, captura todos los campos,
y se detiene en el reCAPTCHA. En cuanto lo marcas, envia el formulario, lee la
pagina de resultado y te devuelve el JSON ya parseado.

Automatiza el trabajo repetitivo entero; lo unico que queda es un clic.

Probado de extremo a extremo contra el INE el 2026-09-10: los selectores, la espera del captcha y la captura del resultado funcionan.

```bash
pip install -r requirements-navegador.txt
playwright install chromium
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/verificacion/asistida   -H "Content-Type: application/json"   -d '{"modelo": "d", "cic": "123456789", "ocr": "1234567890123"}'
```

Detalles que importan:

- **No hay opcion `headless`.** En headless nadie podria marcar el captcha, y
  el intento seria detectado igual. El navegador se abre siempre visible.
- El perfil del navegador es **persistente** (`.navegador-perfil/`), asi que
  las cookies sobreviven entre consultas y no arrancas de cero cada vez.
- La peticion HTTP **queda abierta** mientras esperas (por omision hasta 180 s,
  via `NAVEGADOR_TIMEOUT_CAPTCHA`). Si nadie marca el captcha: `408`.
- Necesita un entorno con escritorio. **En un servidor headless no funciona**,
  y eso es intencional.

### Lo que este proyecto no hace

No resuelve el reCAPTCHA por ti, ni con navegador headless ni con servicios de
terceros. Es el control que el INE puso para distinguir a una persona de un
programa, y saltarlo tampoco seria estable: reCAPTCHA v2 detecta navegadores
automatizados y Cloudflare interpone challenges por encima.

Si necesitas verificacion en volumen y desatendida, la ruta que aguanta
auditoria es un convenio con el INE o un proveedor de identidad autorizado, no
el formulario publico.

## Instalacion

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # Linux / macOS
pip install -r requirements-dev.txt
cp .env.example .env
```

## Ejecucion

```bash
uvicorn app.main:app --reload
```

- Documentacion interactiva: <http://127.0.0.1:8000/docs>
- Salud: <http://127.0.0.1:8000/health>

## Modelos de credencial soportados

Corresponden uno a uno con los formularios del INE:

| `modelo` | Credenciales | Campos requeridos |
|---|---|---|
| `c` | Modelos A, B y C | `clave_elector` (18), `numero_emision` (2), `ocr` (13) |
| `d` | Modelo D | `cic` (9), `ocr` (13) |
| `e` | Modelos E, F, G, H, I y J | `cic` (9), `id_ciudadano` (9) |
| `r` | Reporte de robo o extravio | `numero_reporte` (18) |

Los campos numericos aceptan valores sin los ceros a la izquierda: la API los
rellena antes de enviarlos, porque el formulario del INE si los exige.

## Ejemplos

Validacion local (sin captcha, sin salir a internet):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/validacion/clave-elector \
  -H "Content-Type: application/json" \
  -d '{"clave_elector": "ABCDEF90010109H123"}'
```

```json
{
  "clave": "ABCDEF90010109H123",
  "valida": true,
  "errores": [],
  "fecha_nacimiento": "1990-01-01",
  "clave_entidad": "09",
  "entidad": "CIUDAD DE MEXICO",
  "sexo": "H",
  "edad": 36,
  "mayor_de_edad": true
}
```

Consulta al INE (modelos E/F/G/H):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/verificacion \
  -H "Content-Type: application/json" \
  -d '{
        "modelo": "e",
        "cic": "123456789",
        "id_ciudadano": "987654321",
        "captcha_token": "03AGdBq26..."
      }'
```

## Estructura de la clave de elector

18 caracteres:

```
ABCDEF 900101 09 H 12 3
|      |      |  | |  |
|      |      |  | |  +- digito de disponibilidad
|      |      |  | +---- homoclave del INE
|      |      |  +------ sexo (H / M)
|      |      +--------- entidad de nacimiento (01-32)
|      +---------------- fecha de nacimiento AAMMDD
+----------------------- letras de apellidos y nombre
```

## Pruebas

```bash
pytest -q
```

## Codigos de respuesta de `/api/v1/verificacion`

| Codigo | Significado |
|---|---|
| `200` | El INE respondio; revisa `estatus` |
| `422` | Los datos no cumplen el formato del formulario |
| `424` | Falta `captcha_token`, o el INE lo rechazo |
| `502` | El INE no respondio, o Cloudflare bloqueo la consulta |
| `503` | Consultas salientes deshabilitadas (`CONSULTA_INE_HABILITADA=false`) |

Y en `/api/v1/verificacion/asistida`:

| Codigo | Significado |
|---|---|
| `408` | Nadie marco el reCAPTCHA dentro del tiempo de espera |
| `501` | Playwright no esta instalado |

Valores de `estatus`: `vigente`, `no_vigente`, `no_encontrado`,
`robo_extravio`, `datos_no_coinciden`, `indeterminado`.

`indeterminado` significa que el INE respondio algo que el parser no supo
clasificar. El veredicto original siempre viaja en `mensaje`.

## Que devuelve el INE (verificado en vivo)

Contrastado contra una consulta real el **2026-09-10** (modelo E). La respuesta
trae una tabla de datos y un bloque de veredicto:

```json
{
  "modelo": "e",
  "estatus": "vigente",
  "encontrado": true,
  "mensaje": "Esta vigente como medio de identificacion. Tus datos se encuentran en el Padron Electoral. Sera valida hasta el 31 de diciembre de 2033",
  "vigencia_hasta": "31 de diciembre de 2033",
  "fecha_consulta": "10 de septiembre del 2026",
  "fecha_actualizacion": "10 de septiembre del 2026 03:01",
  "campos": {
    "CIC": "111111111",
    "Clave de elector": "ABCDEF90010109H123",
    "Numero de emision": "1",
    "Distrito Federal": "9",
    "Distrito Local": "9",
    "Numero OCR": "0000000000001",
    "Anio de registro": "2012",
    "Anio de emision": "2023"
  }
}
```

Dos cosas que solo se supieron consultando de verdad, y que estaban mal en la
primera version:

1. **El INE dice "Padron Electoral", no "Lista Nominal".** La frase que
   buscabamos no aparece en ninguna respuesta.
2. **El portal lleva un encabezado fijo que pregunta si tu credencial esta
   vigente, y sale en TODAS las respuestas**, incluidas las negativas.
   Clasificar sobre el texto completo de la pagina da un falso positivo
   garantizado. Por eso el parser aisla primero el bloque de veredicto (los
   `<h4>` y `<p class="lead">` que siguen a la tabla) y solo clasifica ahi
   dentro.

La respuesta real esta congelada, con los datos personales sustituidos por
ficticios, en `tests/fixtures/resultado_vigente.html`. Si el INE cambia el
formato, las pruebas de `tests/test_parser.py` lo delatan.

## Nota sobre datos personales

Los datos de una credencial para votar son datos personales. Consultalos solo
con consentimiento de la persona titular y bajo las obligaciones de la LFPDPPP.
Esta API no persiste nada: recibe, consulta y responde.
