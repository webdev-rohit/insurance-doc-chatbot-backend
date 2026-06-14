from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App settings
    app_name: str = "Insurance Doc Chatbot"

    # CORS
    cors_origins: list[str]

    # GCP settings
    project_id: str
    region: str
    instance_id: str
    # DB -
    db_name: str
    db_user: str
    db_password: str

    # Auth settings
    algorithm: str
    secret_key: str
    access_token_expire_minutes: int
    verify_token_expire_hours: int
    reset_token_expire_minutes: int

    # Email (SendGrid) settings
    sendgrid_api_key: str
    from_email: str

settings = Settings()