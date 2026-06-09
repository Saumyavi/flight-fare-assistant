from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://flight:flight@localhost:5432/flight"

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    WEBHOOK_URL: str = ""
    VALIDATE_TWILIO_SIGNATURE: bool = True

    CRON_SECRET: str = ""
    DEBUG_SECRET: str = ""

    DUFFEL_API_KEY: str = ""

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    ALERT_COOLDOWN_HOURS: int = 6
    DEFAULT_CURRENCY: str = "INR"
    MAX_WATCHES_PER_USER: int = 10
    MAX_SAMPLES_PER_WATCH: int = 5
    PRICE_SAMPLE_RETENTION_DAYS: int = 30


settings = Settings()
