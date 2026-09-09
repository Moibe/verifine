# Verifine

API en FastAPI para validar credenciales para votar (INE) contra el servicio
publico de Lista Nominal: <https://listanominal.ine.mx/scpln/>

La API hace dos cosas distintas, y conviene no confundirlas:

| | Que hace | Necesita internet | Necesita captcha |
|---|---|---|---|
| `/api/v1/validacion/*` | Valida la **estructura** de los datos | No | No |
| `/api/v1/verificacion` | Consulta la **Lista Nominal** del INE | Si | Si |

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
consulta necesita un captcha nuevo resuelto por un humano.

Si Cloudflare bloquea la peticion, la API responde `502` diciendolo, en vez de
inventar un resultado.

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
| `e` | Modelos E, F, G y H | `cic` (9), `id_ciudadano` (9) |
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

Valores de `estatus`: `vigente`, `no_vigente`, `no_encontrado`,
`robo_extravio`, `datos_no_coinciden`, `indeterminado`.

`indeterminado` significa que el INE respondio algo que el parser no supo
clasificar. El texto original siempre viaja en `mensaje`.

## Nota sobre datos personales

Los datos de una credencial para votar son datos personales. Consultalos solo
con consentimiento de la persona titular y bajo las obligaciones de la LFPDPPP.
Esta API no persiste nada: recibe, consulta y responde.
