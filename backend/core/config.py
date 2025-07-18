from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"
    
    openai_api_key: str
    
    # Redis configuration for caching
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = "password"
    
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    debug: bool = False
    
    class Config:
        env_file = ".env"


settings = Settings()
