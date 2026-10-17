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

    # Public base URL of the UI; the Squawk OAuth redirect_uri is {public_url}/login/callback.
    public_url: str = "https://finforge.nathanblatter.com"

    # Squawk — the only sign-in for the UI (https://squawk.nathanblatter.com).
    # Empty squawk_issuer = disabled (local dev): the app then has no way to sign in.
    squawk_issuer: str = ""
    squawk_service_id: str = ""      # FinForge's service id in Squawk (token audience)
    squawk_credential: str = ""      # service credential for client_credentials
    squawk_client_id: str = ""       # public (PKCE) OAuth client for the SPA
    squawk_resource: str = ""        # resource parameter sent to /oauth/authorize
    squawk_owner_username: str = "nathan"  # FinForge user the Squawk owner (sub=owner) maps to

    # Claude AI
    anthropic_api_key: str = ""

    # Cloudflare Tunnel
    tunnel_token: str = ""

    # KPI endpoint
    kpi_api_key: str = ""

    # Flightdeck bug ingest (server-side proxy keeps the ingest key off the client)
    flightdeck_url: str = "http://flightdeck:8080"
    flightdeck_ingest_key: str = ""

    # Outbound email recipients (kept out of source: repo is public)
    report_to_email: str = ""
    reimbursement_to_email: str = ""

    # App
    environment: str = "development"
    log_level: str = "INFO"


# Module-level singleton — import this everywhere
settings = Settings()
