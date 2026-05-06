from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # API Security
    api_key: str

    # Plaid
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"

    # Schwab
    schwab_client_id: str = ""
    schwab_client_secret: str = ""
    schwab_redirect_uri: str = ""
    schwab_token_file: str = "/secrets/schwab_tokens.json"

    # JWT Auth
    jwt_secret: str
    jwt_expire_days: int = 7

    # Claude AI
    anthropic_api_key: str = ""

    # Cloudflare Tunnel
    tunnel_token: str = ""

    # App
    environment: str = "development"
    log_level: str = "INFO"


# Module-level singleton — import this everywhere
settings = Settings()
