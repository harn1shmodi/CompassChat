from pydantic_settings import BaseSettings
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    #use load env variables for sensitive data
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")

    # Database configuration
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./compasschat.db")

    openai_api_key: str = os.getenv("OPENAI_API_KEY")

    # AI Provider Selection
    ai_provider: str = "openai"  # Options: openai, gemini
    gemini_api_key: str = ""
    
    # Model Configuration
    chat_model: str = "gpt-4.1"  # OpenAI models: gpt-4o-mini, gpt-4o, gpt-3.5-turbo
    summarization_model: str = "gpt-4o-mini"  # For summarization tasks
    embedding_model: str = "text-embedding-3-small"  # OpenAI embedding model
    
    # Gemini Model Configuration
    gemini_chat_model: str = "gemini-2.5-pro"  # Gemini models: gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash
    gemini_summarization_model: str = "gemini-2.5-flash"
    
    # Redis configuration for caching
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = "password"
    
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000", "https://chat.gitcompass.com", "https://compasschat-5ap43.ondigitalocean.app"]
    debug: bool = False
    
    # Performance optimization settings
    enable_optimized_embedding: bool = True
    embedding_batch_size: int = 100
    embedding_max_concurrent: int = 5
    embedding_requests_per_minute: int = 300
    
    # Advanced summarization settings
    summarization_strategy: str = "batch_openai"  # Options: batch_openai, batch_anthropic, batch_gemini, selective, traditional
    summarization_batch_size: int = 50
    enable_importance_filtering: bool = True
    enable_hierarchical_summarization: bool = True
    summarization_cost_optimization: bool = True
    
    # Alternative AI provider API keys
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    
    # Intelligent summarization settings
    enable_intelligent_selection: bool = True
    selection_strategy: str = "importance"  # importance, strategic, hybrid, budget
    selection_percentage: float = 0.3  # 30% of chunks
    exclude_test_files: bool = True
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra environment variables without errors


settings = Settings()
