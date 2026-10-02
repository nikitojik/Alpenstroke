from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    apertus_base_url: str = "https://api.publicai.co/v1"
    apertus_api_key: str
    apertus_model: str = "swiss-ai/apertus-70b-instruct"

    database_url: str

settings = Settings()