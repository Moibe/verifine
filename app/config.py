from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Verifine"
    app_version: str = "0.1.0"

    # Origen publico del INE
    ine_base_url: str = "https://listanominal.ine.mx/scpln/"
    ine_resultado_path: str = "resultado.html"
    ine_timeout: float = 30.0
    ine_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    )

    # Interruptor general de las consultas salientes. En false la API solo
    # hace validacion local, util para desarrollo y pruebas.
    consulta_ine_habilitada: bool = True

    # --- Modo asistido con Playwright ---
    # El navegador se abre siempre con interfaz: el reCAPTCHA lo marca una
    # persona. Por eso no hay opcion de headless.
    navegador_perfil_dir: str = ".navegador-perfil"
    navegador_timeout_captcha: float = 180.0
    # El driver de Playwright a veces muere al arrancar (antivirus corporativo,
    # contencion de recursos). Reintentar solo cuesta un segundo y casi siempre
    # resuelve. Nunca se reintenta despues de pedir el captcha.
    navegador_reintentos: int = 2

    # Limite de consultas por minuto por IP, para no golpear al INE.
    rate_limit_por_minuto: int = 10

    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
