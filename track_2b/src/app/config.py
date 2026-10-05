from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env ищем и в текущей папке, и уровнем выше: uvicorn запускается из src/,
    # а .env лежит в корне проекта track_2b/ рядом с docker-compose.yml
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # Имена переменных заданы шаблоном Hack Apertus: LLM_NAME, LLM_BASE_URL, LLM_API_KEY.
    # Любой OpenAI-совместимый сервер с Apertus: Public AI, CSCS, свой vLLM или llama.cpp.
    llm_name: str = "swiss-ai/apertus-70b-instruct"
    llm_base_url: str = "https://api.publicai.co/v1"
    llm_api_key: str

    database_url: str


settings = Settings()
