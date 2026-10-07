from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")
    llm_name: str = "swiss-ai/apertus-70b-instruct"
    llm_base_url: str = "https://api.publicai.co/v1"
    llm_api_key: str
    llm_timeout: float = 60
    database_url: str


settings = Settings()
