from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    openrouter_api_key: str = ""
    ollama_base_url: str = "http://ollama:11434"
    redis_url: str = "redis://redis:6379"
    
    # 支持从父级目录或运行时环境变量读取
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
