"""демонстрирует: конфигурацию через pydantic-settings (.env), провайдеры подменяются без изменения кода."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://app_user:app_secret@localhost:5432/ai_support"
    demo_user_id: str = "00000000-0000-0000-0000-000000000001"
    webhook_secret: str = "dev_webhook_secret"

    llm_provider: str = "mock"           # mock | openai-compatible
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"


settings = Settings()
