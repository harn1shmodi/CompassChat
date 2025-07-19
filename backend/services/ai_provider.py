"""
AI Provider Service - Unified interface for OpenAI and Gemini APIs
"""

from typing import List, Dict, Any, Optional, Generator
import logging
from abc import ABC, abstractmethod
from core.config import settings
from ratelimit import limits, sleep_and_retry

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    @abstractmethod
    def generate_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1000, temperature: float = 0.1) -> str:
        """Generate a chat completion"""
        pass
    
    @abstractmethod
    def generate_streaming_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1000, temperature: float = 0.1) -> Generator[str, None, None]:
        """Generate a streaming chat completion"""
        pass
    
    @abstractmethod
    def generate_embeddings(self, text: str) -> List[float]:
        """Generate embeddings for text"""
        pass


class OpenAIProvider(AIProvider):
    """OpenAI API provider implementation"""
    
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.chat_model = settings.chat_model
        self.summarization_model = settings.summarization_model
        self.embedding_model = settings.embedding_model
        logger.info(f"OpenAI provider initialized with models: chat={self.chat_model}, embedding={self.embedding_model}")
    
    @sleep_and_retry
    @limits(calls=50, period=60)  # 50 calls per minute
    def generate_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1000, temperature: float = 0.1) -> str:
        """Generate a chat completion using OpenAI"""
        try:
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI chat completion error: {e}")
            raise
    
    @sleep_and_retry
    @limits(calls=50, period=60)  # 50 calls per minute
    def generate_streaming_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1000, temperature: float = 0.1) -> Generator[str, None, None]:
        """Generate a streaming chat completion using OpenAI"""
        try:
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True
            )
            
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"OpenAI streaming completion error: {e}")
            raise
    
    @sleep_and_retry
    @limits(calls=100, period=60)  # 100 calls per minute for embeddings
    def generate_embeddings(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI"""
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.embedding_model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embeddings error: {e}")
            raise
    
    def generate_summarization(self, messages: List[Dict[str, str]], max_tokens: int = 500, temperature: float = 0.1) -> str:
        """Generate summarization using OpenAI"""
        try:
            response = self.client.chat.completions.create(
                model=self.summarization_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI summarization error: {e}")
            raise


class GeminiProvider(AIProvider):
    """Google Gemini API provider implementation"""
    
    def __init__(self):
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            self.client = genai
            self.chat_model = settings.gemini_chat_model
            self.summarization_model = settings.gemini_summarization_model
            
            # Initialize models
            self.chat_model_instance = genai.GenerativeModel(self.chat_model)
            self.summarization_model_instance = genai.GenerativeModel(self.summarization_model)
            
            logger.info(f"Gemini provider initialized with models: chat={self.chat_model}, summarization={self.summarization_model}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini provider: {e}")
            raise
    
    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, str]]) -> str:
        """Convert OpenAI-style messages to Gemini format"""
        prompt_parts = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"Instructions: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        
        return "\n\n".join(prompt_parts)
    
    @sleep_and_retry
    @limits(calls=40, period=60)  # 40 calls per minute for Gemini
    def generate_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1000, temperature: float = 0.1) -> str:
        """Generate a chat completion using Gemini"""
        try:
            prompt = self._convert_messages_to_gemini_format(messages)
            
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
                "top_k": 64,
            }
            
            response = self.chat_model_instance.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            return response.text
        except Exception as e:
            logger.error(f"Gemini chat completion error: {e}")
            raise
    
    @sleep_and_retry
    @limits(calls=40, period=60)  # 40 calls per minute for Gemini
    def generate_streaming_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1000, temperature: float = 0.1) -> Generator[str, None, None]:
        """Generate a streaming chat completion using Gemini"""
        try:
            prompt = self._convert_messages_to_gemini_format(messages)
            
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
                "top_k": 64,
            }
            
            response = self.chat_model_instance.generate_content(
                prompt,
                generation_config=generation_config,
                stream=True
            )
            
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini streaming completion error: {e}")
            raise
    
    def generate_embeddings(self, text: str) -> List[float]:
        """Generate embeddings using Gemini (falls back to OpenAI for now)"""
        # Note: Gemini doesn't have a direct embeddings API similar to OpenAI
        # For now, we'll fall back to OpenAI for embeddings
        logger.warning("Gemini embeddings not available, falling back to OpenAI")
        
        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=settings.openai_api_key)
            response = openai_client.embeddings.create(
                input=text,
                model=settings.embedding_model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Fallback OpenAI embeddings error: {e}")
            raise
    
    def generate_summarization(self, messages: List[Dict[str, str]], max_tokens: int = 500, temperature: float = 0.1) -> str:
        """Generate summarization using Gemini"""
        try:
            prompt = self._convert_messages_to_gemini_format(messages)
            
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
                "top_k": 64,
            }
            
            response = self.summarization_model_instance.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            return response.text
        except Exception as e:
            logger.error(f"Gemini summarization error: {e}")
            raise


class AIProviderFactory:
    """Factory class for creating AI providers"""
    
    @staticmethod
    def create_provider() -> AIProvider:
        """Create an AI provider based on configuration"""
        provider_type = settings.ai_provider.lower()
        
        if provider_type == "openai":
            return OpenAIProvider()
        elif provider_type == "gemini":
            if not settings.gemini_api_key:
                logger.error("Gemini API key not configured, falling back to OpenAI")
                return OpenAIProvider()
            return GeminiProvider()
        else:
            logger.warning(f"Unknown AI provider: {provider_type}, defaulting to OpenAI")
            return OpenAIProvider()


# Global provider instance
ai_provider = AIProviderFactory.create_provider()