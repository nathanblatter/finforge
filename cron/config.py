from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    api_key: str

    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"

    schwab_client_id: str = ""
    schwab_client_secret: str = ""
    schwab_token_file: str = "/secrets/schwab_tokens.json"
    schwab_account_map: str = ""  # JSON: {"account_number": "alias", ...}

    anthropic_api_key: str = ""

    # Outbound email recipient (kept out of source: repo is public)
    report_to_email: str = ""

    # iMessage delivery gateway (imessage-api server on the Mac Mini, Tailscale-bound)
    imessage_api_url: str = "http://100.79.61.79:8899"
    imessage_api_key: str = ""
    imessage_recipient: str = ""

    environment: str = "development"
    log_level: str = "INFO"


settings = Settings()
